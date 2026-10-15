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
    if path.is_symlink() or (path.exists() and not path.is_file()):
        return None
    if path.exists():
        try:
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
                db.execute('PRAGMA query_only=ON')
                row = db.execute('SELECT origin_session_id,state,result_json FROM async_delegations WHERE delegation_id=?', (key,)).fetchone()
            if row:
                if (row[0] and row[0] != receipt['session_id']) or row[1] not in TERMINAL:
                    return None
                # Existing but corrupt evidence is NOT absence. Never fall back on it.
                result = json.loads(row[2])
                if not isinstance(result, dict):
                    return None
                native = {'state': row[1], 'result': result, 'delegation_id': key}
        except (sqlite3.Error, ValueError, TypeError):
            return None
    durable_state = None
    if native is not None:
        from .followup import protocol_outcomes, native_pending, native_failed
        states = [str(x.get('state', x.get('status', ''))).lower() for x in protocol_outcomes(native)]
        if native_pending(native) or 'unknown' in states:
            return None
        durable_state = ('interrupted' if 'interrupted' in states else 'cancelled' if states[0] == 'cancelled'
                         else 'failed' if native_failed(native) else states[0])
    files = Files(home)
    files.root = home / 'cache/delegation/live'
    manifest_state = None
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
        manifest_state = ('interrupted' if 'interrupted' in states else 'completed' if all(s == 'completed' for s in states)
                          else 'cancelled' if all(s == 'cancelled' for s in states) else 'failed')
    except FileNotFoundError:
        pass  # Only genuine absence permits the other native source to stand alone.
    except (OSError, ValueError, TypeError):
        return None
    if durable_state and manifest_state and durable_state != manifest_state:
        return None
    state = durable_state or manifest_state
    if state is None:
        return None
    return {'native_status': state, 'terminal': True, 'failed': state != 'completed',
            'terminal_evidence': 'native_durable' if durable_state else 'native_manifest'}


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
                    if (isinstance(text, str) and digest(text) == reply.get('assistant_hash')
                            and (not reply.get('content_hash') or revision(text.encode()) == reply['content_hash'])):
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
    """Only complete literal inquiries; free text always retains semantic review."""
    if not row.get('ended') or row.get('failed') or row.get('interrupted') or row.get('disposition') != 'pending':
        return False
    signal = view.record('signal', row['signal_id']) or {}
    text = signal.get('text', '').strip()
    if signal.get('truncated') or digest(text) != row.get('user_hash'):
        return False
    # Closed complete utterances only: never infer that arbitrary topic/prefix text
    # lacks an instruction. Everything else needs the existing semantic review.
    if text.casefold() not in {
        "what is the status?", "what's the status?", "what is the current status?",
        "what time is it?", "what is the version?",
        "状态如何？", "现在状态如何？", "目前状态如何？", "什么版本？", "几点了？",
    }:
        return False
    if any(r.get('turn_id') == row['signal_id'] and r.get('session_id') == row['session_id'] for r in view.rows('followup_receipt')):
        return False
    reply, history = exact_reply(view.home, {'session_id': row['session_id'], 'assistant_hash': row.get('assistant_hash'), 'message_id': row.get('assistant_message_id')}, since=signal['created'])
    if not reply or history['messages'][0].get('at', 0) < signal['created']:
        return False
    answer = next(m['text'] for m in history['messages'] if m['id'] == reply['message_id'])
    if re.search(r"(?i)(\bwill\b|\bshall\b|\blater\b|我会|稍后|将会|待确认)", answer):
        return False
    return True


def objects(view):
    rows = [(kind, r['id'], r) for kind in KINDS[:2] for r in view.rows(kind)]
    for path in sorted((view.home / 'muse/workspace/goals').glob('*/GOAL.md')):
        _, row, _ = view.object('goal', path.parent.name)
        rows.append(('goal', row['id'], row))
    return sorted(rows, key=lambda x: x[0] + ':' + x[1])


def recovery_blocker(view, goal, *, session_id="", turn_id=""):
    fu = goal.get('followup')
    if not fu:
        return None
    from .followup import newer_input
    return newer_input(goal, fu, view.record, turns=view.rows('followup_turn'), session_id=session_id, turn_id=turn_id)


def proposed(view, kind, row, now, **origin):
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
            after.update(disposition='no_commitment', reason='Native settled answer to a complete literal inquiry; no accepted work', revision=row['revision'] + 1)
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
        from .delivery import basis, valid_basis
        replies = view.rows('followup_reply')
        if valid_basis(fu, {'followup_reply': replies, 'notification': view.rows('notification')}):
            return None
        from .delivery import reviewed_reply
        review = view.record('followup_handoff', row['id'])
        if review:
            r = next((r for r in replies if r['id'] == review.get('reply_id')), None)
            if r:
                reply, history = exact_reply(view.home, r, since=fu.get('source_created_at', row['created']))
                if reply and reviewed_reply(row, reply, history, review):
                    after['followup'].update(delivery_basis=basis(fu, 'reply', r['id'], 'recorded_unconfirmed', now),
                        reply_id=r['id'], delivery_state='unknown', blocker_class='delivery_unknown', revision=fu['revision'] + 1)
    return after if after != row else None


def diagnose(home, data, now, **origin):
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
        after = proposed(view, kind, row, now, **origin)
        blocker = recovery_blocker(view, row, **origin) if kind == 'goal' and after else None
        items.append({'object_kind': kind, 'id': key, 'expected_revision': revision(canonical(row)),
                      'repair_ids': [r['id'] for r in repairs if r['kind'] == kind and r['key'] == key][-5:],
                      'change': after is not None and not blocker, 'blocked_by': blocker, 'reason': 'newer_input_review_required' if blocker else 'native_evidence' if after else 'unchanged_or_unproven'})
    return {'scope_token': view.scope(), 'items': items,
            'next_cursor': selected[-1][0] + ':' + selected[-1][1] if len(selected) == 10 else None,
            'pagination': 'Lexical object keys; new earlier IDs require a fresh pass. Apply rechecks each current object and native evidence; no snapshot claims.',
            'mode': 'dry_run'}


def apply(followups, data, now, **origin):
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
            if backup.get('parent_session'):
                from .runtime import session_info
                from agent.delegation_context import is_delegated_child_context
                info = session_info()
                if (origin.get('session_id') != backup['parent_session'] or info['cron']
                        or info.get('platform') in {'cron', 'delegate', 'subagent', 'webhook', 'kanban'}
                        or is_delegated_child_context()):
                    raise DomainError('permission_denied', 'Binding rollback requires its original private parent')
            if row != backup['after'] and not (backup.get('state') == 'pending' and row == backup['before']):
                raise DomainError('revision_conflict', 'Post-repair state changed; rollback cannot overwrite it')
            after = backup['before']
        else:
            after = proposed(view, kind, row, now, **origin)
            blocker = recovery_blocker(view, row, **origin) if kind == 'goal' and after else None
            if blocker:
                raise DomainError('permission_denied', 'Review newer user input before background followup', continuation=blocker)
        if after is None or (after == row and not backup):
            return {'changed': False, 'revision': current}
        if kind == 'goal':
            if not backup:
                with store.transaction() as db:
                    followups._gate(db, row, row['followup'], allow_terminal=True, **origin)
            after = copy.deepcopy(after)
            after.pop('_request_id', None)
        related = backup.get('related', []) if backup else []
        for item in related:
            current_related = store.read(item['kind'], item['key'])
            if current_related != item['after'] and not (backup.get('state') == 'pending' and current_related == item['before']):
                raise DomainError('revision_conflict', 'Related binding changed; rollback cannot overwrite it')
        if related and any(g.get('followup', {}).get('reply_id') == related[0]['key']
                           for g in store.goals()):
            raise DomainError('revision_conflict', 'Reply already used by handoff; retain its evidence')
        return save_repair(store, kind, key, row, after, body if kind == 'goal' else None,
                           fingerprint if kind == 'goal' else None, backup=backup)


def save_repair(store, kind, key, before, after, body=None, fingerprint=None, *, related=(), backup=None, parent_session=None):
    """Shared durable preimage for convergence and explicit bindings; caller holds lock."""
    repair_id = digest(canonical([kind, key, before, after]).decode())
    saved = backup or {'id': repair_id, 'kind': kind, 'key': key, 'before': before,
                       'after': after, 'state': 'pending', 'related': list(related), 'parent_session': parent_session}
    if not backup:
        store.write('followup_repair', repair_id, saved)
    with store.transaction() as db:
        for item in saved.get('related', []):
            value = item['before'] if backup else item['after']
            if value is None:
                store.delete(db, item['kind'], item['key'])
            else:
                store.put(db, item['kind'], item['key'], value)
        if kind == 'goal':
            store.save_goal(after, body, expected_hash=fingerprint)
        else:
            store.put(db, kind, key, after)
        saved['state'] = 'rolled_back' if backup else 'applied'
        store.put(db, 'followup_repair', saved['id'], saved)
    return {'changed': True, 'repair_id': saved['id'], 'revision': revision(canonical(after)),
            'mode': 'rollback' if backup else 'apply',
            'delivery_note': 'Recorded reply is not transport confirmation or proof of reading.'}


def successor_evidence(service, goal, receipt_id, refs):
    """Same-profile native owner terminal proof plus explicit parent result references."""
    from .evidence import resolve
    view = Views(service.store.home)
    receipt = view.record('followup_receipt', receipt_id) or {}
    if (receipt.get('session_id') != goal['session_id'] or not receipt.get('tool_call_id')
            or receipt.get('observed_at', 0) < goal['followup'].get('source_created_at', goal['created'])
            or receipt_id == goal['followup'].get('receipt_id')):
        raise DomainError('permission_denied', 'Successor needs a distinct native receipt from this goal session after acceptance')
    intent = view.record('followup_intent', receipt.get('intent_id')) if receipt.get('intent_id') else None
    if intent and intent.get('goal_id') != goal['id']:
        raise DomainError('permission_denied', 'Successor is bound to another goal')
    if receipt.get('owner') == goal['followup'].get('owner'):
        raise DomainError('permission_denied', 'Successor cannot be the original owner')
    native = native_terminal(service.store.home, receipt)
    if not native or native['native_status'] != 'completed' or native['failed']:
        raise DomainError('source_unavailable', 'Successor native execution is not proven completed')
    if not isinstance(refs, list) or not refs or any(r.get('kind') != 'native_message' or not r.get('hash') for r in refs if isinstance(r, dict)):
        raise DomainError('invalid_argument', 'Successor needs exact native_message evidence with full hashes')
    resolved = resolve(service, refs, goal)
    with sqlite3.connect((service.store.home / 'state.db').as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        for ref in refs:
            at, role, tool, call = db.execute('SELECT timestamp,role,tool_name,tool_call_id FROM messages WHERE id=? AND session_id=?', (ref['message_id'], goal['session_id'])).fetchone()
            if at < goal['followup'].get('source_created_at', goal['created']):
                raise DomainError('permission_denied', 'Successor evidence predates accepted goal')
            if role == 'assistant' and at < receipt['observed_at']:
                raise DomainError('permission_denied', 'Assistant result predates successor receipt')
            if role == 'tool' and (tool != 'delegate_task' or call != receipt['tool_call_id']):
                raise DomainError('permission_denied', 'Tool result is not this successor call')
    return {'receipt_id': receipt_id, 'owner': receipt['owner'], 'native': native,
            'scope_revision': goal['followup']['scope_revision'], 'evidence_refs': resolved,
            'original_receipt_id': goal['followup'].get('receipt_id'),
            'original_owner': goal['followup'].get('owner'), 'original_intent_id': goal['followup'].get('intent_id')}


def successful_successor(service, goal):
    bound = goal.get('followup', {}).get('successor') or {}
    if bound.get('scope_revision') != goal['followup']['scope_revision']:
        return False
    try:
        current = successor_evidence(service, goal, bound.get('receipt_id'), [r['ref'] for r in bound.get('evidence_refs', [])])
        return all(current[k] == bound.get(k) for k in ('owner', 'original_receipt_id', 'original_owner', 'original_intent_id'))
    except (ValueError, KeyError, TypeError, sqlite3.Error):
        return False


def rebind(followups, data, now, *, session_id='', turn_id=''):
    from .locks import file_lock
    from .store import bounded
    store = followups.store
    view = Views(store.home)
    view.check_scope(data.get('scope_token'))
    with file_lock(store.root / 'mutations.lock'):
        goal, body, fingerprint = store.goal(identifier(data['goal_id']), with_fingerprint=True)
        if not session_id or session_id != goal.get('session_id'):
            raise DomainError('permission_denied', 'Binding requires the original goal parent session')
        fu = goal.get('followup')
        if not fu or data.get('expected_revision') != fingerprint:
            raise DomainError('revision_conflict', 'Reread current goal content revision')
        with store.transaction() as db:
            followups._gate(db, goal, fu, session_id=session_id, turn_id=turn_id, allow_terminal=True)
        reason = bounded(data.get('reason'), 2000)
        if not reason.strip():
            raise DomainError('invalid_argument', 'Explicit parent semantic binding reason required')
        after = copy.deepcopy(goal)
        related = []
        if data['binding'] == 'reply':
            mid, hash_value = data.get('message_id'), data.get('message_hash')
            if type(mid) is not int or not isinstance(hash_value, str) or not re.fullmatch(r'[0-9a-f]{64}', hash_value):
                raise DomainError('invalid_argument', 'Use exact native assistant message_id and full SHA256')
            if (store.home / 'state.db').is_symlink() or not (store.home / 'state.db').is_file():
                raise DomainError('source_unavailable', 'Native history unavailable')
            # exact_reply uses the legacy short digest; the public binding requires full SHA256.
            with sqlite3.connect((store.home / 'state.db').as_uri() + '?mode=ro', uri=True) as db:
                db.execute('PRAGMA query_only=ON')
                native = db.execute('SELECT content,timestamp FROM messages WHERE id=? AND session_id=?', (mid, session_id)).fetchone()
            if not native or not isinstance(native[0], str) or revision(native[0].encode()) != hash_value:
                raise DomainError('permission_denied', 'Native message missing or full hash mismatch')
            row = {'session_id': session_id, 'message_id': mid, 'assistant_hash': digest(native[0])}
            reply, _ = exact_reply(store.home, row, since=fu.get('source_created_at', goal['created']))
            if not reply or native[1] <= fu.get('source_created_at', goal['created']):
                raise DomainError('permission_denied', 'Binding needs a final assistant reply after goal acceptance')
            binding = {'goal_id': goal['id'], 'scope_revision': fu['scope_revision'],
                       'verification_revision': revision(canonical(fu.get('verification', {})))}
            key = digest(canonical([binding, mid, hash_value]).decode())
            reply.update(id=key, observed_at=native[1], historical_binding=binding, content_hash=hash_value)
            before = store.read('followup_reply', key)
            if before is not None and before != reply:
                raise DomainError('revision_conflict', 'Existing reply reference differs')
            related.append({'kind': 'followup_reply', 'key': key, 'before': before, 'after': reply})
            after['followup']['bound_reply_id'] = key
        else:
            if fu['execution_state'] in {'paused', 'needs_user', 'cancelled'}:
                raise DomainError('permission_denied', 'Successor cannot reopen a closed or paused goal')
            successor = successor_evidence(followups.service, goal, data.get('receipt_id'), data.get('evidence_refs'))
            successor.update(reason=reason, bound_at=now)
            after['followup'].update(successor=successor, execution_state='finished', result_state='unverified',
                                     delivery_state='open', delivery_basis=None, blocker_class=None)
        after['followup']['revision'] += 1
        result = save_repair(store, 'goal', goal['id'], goal, after, body, fingerprint, related=related, parent_session=session_id)
        result['goal_revision'] = store.goal(goal['id'], with_fingerprint=True)[2]
        result['followup_revision'] = after['followup']['revision']
        if related:
            result['reply_id'] = related[0]['key']
        return result



def automatic(followups, session_id, now, owner_id=None):
    """Existing hooks only; bounded work, no polling or new wakeups."""
    view = Views(followups.store.home)
    rows = [r for r in objects(view) if (session_id is None or r[2].get('session_id') == session_id)
            and (not owner_id or (r[2].get('owner') or {}).get('id') == owner_id)]
    rows = [r for r in rows if not (r[0] == 'followup_receipt' and r[2].get('terminal') and r[2].get('native_status') in TERMINAL)
            and not (r[0] == 'followup_turn' and r[2].get('disposition') not in {'pending', 'needs_clarification'})]
    if session_id is not None and not owner_id:
        # Settle completed inquiries before evaluating the older goal's input gate.
        rows.sort(key=lambda r: (r[0] != 'followup_turn', -r[2].get('created', 0)))
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
