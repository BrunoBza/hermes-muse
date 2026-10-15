"""Evidence-only convergence; no dispatch, transport, model or new scheduler."""
import copy
import json
import re
import sqlite3

from .content_io import DomainError, Files, revision
from .store import digest, identifier
from .views import Views, canonical

KINDS = ('followup_receipt', 'followup_turn', 'goal')
TERMINAL = {'completed', 'interrupted', 'failed', 'cancelled', 'error', 'timeout', 'stalled'}


def native_terminal(home, receipt):
    """Pinned native schemas, read-only. The tool-hook receipt supplies owner identity.

    get_durable_delegation initializes native schema, so it is not a pure read API.
    Never trust completion-message text or worker-written transcript body as status.
    """
    owner = receipt.get('owner') or {}
    key = owner.get('id', '')
    if owner.get('kind') != 'native_delegation' or not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', key):
        return None
    native = None
    path = home / 'state.db'
    if path.is_file() and not path.is_symlink():
        try:
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
                db.execute('PRAGMA query_only=ON')
                row = db.execute('SELECT origin_session_id,state,result_json FROM async_delegations WHERE delegation_id=?', (key,)).fetchone()
            if row:
                if row[0] and row[0] != receipt['session_id']:
                    return None
                native = {'state': row[1], 'result': json.loads(row[2] or '{}'), 'delegation_id': key}
        except (sqlite3.Error, ValueError):
            pass
    if native is not None:
        if not isinstance(native['result'], dict):
            return None
        from .followup import protocol_outcomes, native_pending, native_failed
        states = [str(x.get('state', x.get('status', ''))).lower() for x in protocol_outcomes(native)]
        if states[0] not in TERMINAL or native_pending(native) or 'unknown' in states:
            return None
        state = 'interrupted' if 'interrupted' in states else 'failed' if native_failed(native) else states[0]
        return {'native_status': state, 'terminal': True, 'failed': state != 'completed', 'terminal_evidence': 'native_durable'}
    # The native aggregate manifest is written by the host after all children settle.
    # Reuse descriptor-relative no-follow reads, never paths supplied by the model/manifest.
    files = Files(home)
    files.root = home / 'cache/delegation/live'
    try:
        raw = files.read(key + '/manifest.json')
        if len(raw) > 262144:
            return None
        manifest = json.loads(raw)
        if not isinstance(manifest, dict):
            return None
        tasks = manifest.get('tasks', [])
        if not isinstance(tasks, list) or any(not isinstance(t, dict) or not isinstance(t.get('index'), int) for t in tasks):
            return None
        if (manifest.get('delegation_id') != key or not manifest.get('completed') or not tasks
                or len(tasks) != manifest.get('task_count') or len(tasks) > 100
                or sorted(t.get('index') for t in tasks) != list(range(len(tasks)))):
            return None
        states = [t.get('status') for t in tasks]
        if any(s not in TERMINAL for s in states):
            return None
        state = 'interrupted' if 'interrupted' in states else 'completed' if all(s == 'completed' for s in states) else 'failed'
        return {'native_status': state, 'terminal': True, 'failed': state != 'completed', 'terminal_evidence': 'native_manifest'}
    except (OSError, ValueError, TypeError):
        return None


def exact_reply(home, reply, history=None, *, since=0):
    if history is None:
        history = {'available': False, 'messages': []}
        path = home / 'state.db'
        if not path.is_file() or path.is_symlink():
            return None, history
        try:
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
                db.execute('PRAGMA query_only=ON')
                session = db.execute('SELECT chat_type FROM sessions WHERE id=?', (reply['session_id'],)).fetchone()
                if not session or str(session[0]).lower() in {'group', 'supergroup', 'channel', 'guild', 'room'}:
                    return None, history
                sql = "SELECT id,content,timestamp FROM messages WHERE session_id=? AND role='assistant' AND (tool_calls IS NULL OR tool_calls='[]') AND (display_kind IS NULL OR display_kind!='hidden')"
                sql += ' AND timestamp>=?'
                args = [reply['session_id'], since]
                if reply.get('message_id') is not None:
                    sql += ' AND id=?'
                    args.append(reply['message_id'])
                # Hash stream when old hooks lacked row IDs; no transcript copies/preview limits.
                matches = []
                for mid, text, at in db.execute(sql, args):
                    if isinstance(text, str) and digest(text) == reply.get('assistant_hash'):
                        matches.append({'id': mid, 'role': 'assistant', 'text': text, 'at': at})
                        if len(matches) > 1:
                            break
                history = {'available': True, 'messages': matches}
        except sqlite3.Error:
            return None, history
    matches = [m for m in history.get('messages', []) if m['role'] == 'assistant'
               and digest(m['text']) == reply.get('assistant_hash')
               and (reply.get('message_id') is None or m['id'] == reply['message_id'])]
    if not history.get('available') or len(matches) != 1:
        return None, history
    return {**reply, 'message_id': matches[0]['id']}, history


def answered_question(view, row):
    """Only narrow status/factual questions; ambiguous requests retain semantic review."""
    if not row.get('ended') or row.get('failed') or row.get('interrupted') or row.get('disposition') != 'pending':
        return False
    signal = view.record('signal', row['signal_id']) or {}
    text = signal.get('text', '').strip()
    if signal.get('truncated') or digest(text) != row.get('user_hash'):
        return False
    if not re.match(r"(?i)^(what(?:'s| is) (?:the |its |current )?(?:status|time|version)|how (?:is|are) .*|.*(?:状态如何|怎么样了|什么版本|几点了))[?？。!！ ]*$", text):
        return False
    if any(r.get('turn_id') == row['signal_id'] for r in view.rows('followup_receipt')):
        return False
    reply, history = exact_reply(view.home, {'session_id': row['session_id'], 'assistant_hash': row.get('assistant_hash'), 'message_id': row.get('assistant_message_id')}, since=signal['created'])
    if not reply or history['messages'][0].get('at', 0) < signal['created']:
        return False
    answer = next(m['text'] for m in history['messages'] if m['id'] == reply['message_id'])
    if re.search(r"(?i)(\?|？|\bwill\b|\bshall\b|\blater\b|我会|稍后|将会|待确认)", answer):
        return False
    return True


def objects(view):
    rows = [(kind, r['id'], r) for kind in KINDS[:2] for r in view.rows(kind)]
    for path in sorted((view.home / 'muse/workspace/goals').glob('*/GOAL.md')):
        _, row, _ = view.object('goal', path.parent.name)
        rows.append(('goal', row['id'], row))
    return sorted(rows, key=lambda x: x[0] + ':' + x[1])


def proposed(view, kind, row, now):
    after = copy.deepcopy(row)
    if kind == 'followup_receipt':
        if row.get('terminal') and row.get('native_status') in TERMINAL:
            return None
        evidence = native_terminal(view.home, row)
        if evidence:
            after.update(evidence)
    elif kind == 'followup_turn':
        if any(g.get('source_signal') == row['signal_id'] for k, _, g in objects(view) if k == 'goal'):
            return None
        if answered_question(view, row):
            after.update(disposition='no_commitment', reason='Native settled answer to a narrow status/factual question; no accepted work', revision=row['revision'] + 1)
    else:
        fu = row.get('followup') or {}
        receipt = view.record('followup_receipt', fu.get('receipt_id', '')) or {}
        if (row.get('status') == 'active' and fu.get('intent_id') and receipt.get('intent_id') == fu['intent_id']
                and receipt.get('scope_revision') == fu.get('scope_revision') and receipt.get('terminal')
                and receipt.get('native_status') in TERMINAL and fu.get('execution_state') in {'waiting_external', 'outcome_unknown'}):
            after['followup'].update(execution_state='finished', blocker_class=None, revision=fu['revision'] + 1, next_check_at=now)
            return after
        if (row.get('status') == 'cancelled' or fu.get('result_state') != 'verified'
                or fu.get('delivery_state') in {'confirmed', 'suppressed'}):
            return None
        from .delivery import reply_evidence, basis, valid_basis
        replies = view.rows('followup_reply')
        if valid_basis(fu, {'followup_reply': replies, 'notification': view.rows('notification')}):
            return None
        for r in sorted(replies, key=lambda r: r['observed_at'], reverse=True):
            since = max(fu.get('source_created_at', row['created']), fu.get('verification', {}).get('verified_at', 0))
            if r.get('session_id') != row.get('session_id') or r.get('observed_at', 0) < since:
                continue
            reply, history = exact_reply(view.home, r, since=since)
            if (reply and history['messages'][0].get('at', 0) >= max(fu.get('source_created_at', row['created']), fu.get('verification', {}).get('verified_at', 0))
                    and reply_evidence(row, reply, history)[1]):
                after['followup'].update(delivery_basis=basis(fu, 'reply', r['id'], 'recorded_unconfirmed', now),
                    reply_id=r['id'], delivery_state='unknown', blocker_class='delivery_unknown', revision=fu['revision'] + 1)
                break
    return after if after != row else None


def diagnose(home, data, now):
    view = Views(home)
    view.check_scope(data.get('scope_token'))
    all_rows = objects(view)
    repairs = view.rows('followup_repair')
    cursor = data.get('cursor', '')
    if not isinstance(cursor, str) or len(cursor) > 300:
        raise DomainError('invalid_argument', 'cursor must be a bounded object key')
    selected = [r for r in all_rows if r[0] + ':' + r[1] > cursor][:10]
    items = []
    for kind, key, row in selected:
        after = proposed(view, kind, row, now)
        items.append({'object_kind': kind, 'id': key, 'expected_revision': revision(canonical(row)),
                      'repair_ids': [r['id'] for r in repairs if r['kind'] == kind and r['key'] == key][-5:],
                      'change': after is not None, 'reason': 'native_evidence' if after else 'unchanged_or_unproven'})
    return {'scope_token': view.scope(), 'items': items,
            'next_cursor': selected[-1][0] + ':' + selected[-1][1] if len(selected) == 10 else None,
            'pagination': 'Lexical object keys; new earlier IDs require a fresh pass. Apply rechecks each current object and native evidence; no snapshot claims.',
            'mode': 'dry_run'}


def apply(followups, data, now):
    """One object, original evidence, CAS, durable preimage and guarded rollback."""
    store = followups.store
    view = Views(store.home)
    view.check_scope(data.get('scope_token'))
    mode = data.get('mode', 'dry_run')
    if mode not in {'apply', 'rollback'}:
        raise DomainError('invalid_argument', 'mode must be dry_run/apply/rollback')
    from .locks import file_lock
    with file_lock(store.root / 'mutations.lock'):
        backup = store.read('followup_repair', identifier(data['repair_id'])) if mode == 'rollback' else None
        if mode == 'rollback' and not backup:
            raise DomainError('not_found', 'Repair backup unavailable')
        kind = backup['kind'] if backup else data.get('object_kind')
        key = backup['key'] if backup else identifier(data.get('id'))
        if kind not in KINDS:
            raise DomainError('invalid_argument', 'Unsupported followup object')
        if kind == 'goal':
            row, body, fingerprint = store.goal(key, with_fingerprint=True)
        else:
            row = store.read(kind, key)
        if row is None:
            raise DomainError('not_found', 'Followup object unavailable')
        current = revision(canonical(row))
        if data.get('expected_revision') != current:
            raise DomainError('revision_conflict', 'Reread the followup object', current_revision=current)
        if backup:
            if row != backup['after']:
                raise DomainError('revision_conflict', 'Post-repair state changed; rollback cannot overwrite it')
            after = backup['before']
        else:
            after = proposed(view, kind, row, now)
        if after is None or after == row:
            return {'changed': False, 'revision': current}
        if kind == 'goal':
            if not backup:
                with store.transaction() as db:
                    followups._gate(db, row, row['followup'], allow_terminal=True)
            after = copy.deepcopy(after)
            after.pop('_request_id', None)
        repair_id = digest(canonical([kind, key, row, after]).decode())
        # Evidence first: a crash leaves a pending preimage, never a forced DB restore.
        if not backup:
            store.write('followup_repair', repair_id, {'id': repair_id, 'kind': kind, 'key': key, 'before': row, 'after': after, 'state': 'pending'})
        if kind == 'goal':
            store.save_goal(after, body, expected_hash=fingerprint)
        else:
            store.write(kind, key, after)
        saved = backup or store.read('followup_repair', repair_id)
        saved['state'] = 'rolled_back' if backup else 'applied'
        store.write('followup_repair', saved['id'], saved)
        return {'changed': True, 'repair_id': saved['id'], 'revision': revision(canonical(after)), 'mode': mode,
                'delivery_note': 'Recorded reply is not transport confirmation or proof of reading.'}


def automatic(followups, session_id, now, owner_id=None):
    """Existing hooks only; bounded work, no polling or new wakeups."""
    view = Views(followups.store.home)
    rows = [r for r in objects(view) if (session_id is None or r[2].get('session_id') == session_id)
            and (not owner_id or (r[2].get('owner') or {}).get('id') == owner_id)]
    rows = [r for r in rows if not (r[0] == 'followup_receipt' and r[2].get('terminal') and r[2].get('native_status') in TERMINAL)
            and not (r[0] == 'followup_turn' and r[2].get('disposition') not in {'pending', 'needs_clarification'})]
    cursor = getattr(followups, '_recovery_after', '') if session_id is None else ''
    selected = [r for r in rows if r[0] + ':' + r[1] > cursor][:25]
    if not selected:
        selected = rows[:25]
    if session_id is None and selected:
        followups._recovery_after = selected[-1][0] + ':' + selected[-1][1]
    for kind, key, row in selected:
        try:
            if proposed(view, kind, row, now):
                apply(followups, {'mode': 'apply', 'object_kind': kind, 'id': key,
                                 'expected_revision': revision(canonical(row))}, now)
        except (OSError, ValueError):
            continue  # Native evidence remains available for explicit diagnosis/retry.
