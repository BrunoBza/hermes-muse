"""Read native conversation evidence without copying or writing session history."""
import json
from contextlib import nullcontext
from .store import digest, is_background_message


def read_conversation(home, session_id, since):
    path = home / "state.db"
    empty = {"session_id": session_id, "available": True, "revision": digest("[]"), "messages": []}
    if not path.exists():
        return {**empty, "note": "No native history exists yet; not proof of task completion."}
    db = None
    try:
        from hermes_state import SessionDB
        db = SessionDB(db_path=path, read_only=True)
        session = db.get_session(session_id)
        if not session:
            return {**empty, "note": "Session not found; use source evidence or native retrieval if needed."}
        if str(session.get("chat_type", "")).lower() in {"group", "supergroup", "channel", "guild", "room"}:
            return {**empty, "available": False, "error": "Group conversation is outside private companion scope."}
        messages, offset = [], 0
        while True:
            page = db.get_messages(session_id, include_compacted=True, limit=200, offset=offset, latest=True)
            if not page:
                break
            for row in page:
                role, content = row.get("role"), row.get("content")
                if (row.get("timestamp", 0) < since or role not in {"user", "assistant"}
                        or not content or row.get("tool_calls") or row.get("display_kind") == "hidden"):
                    continue
                text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                if text.strip() == "[SILENT]":
                    continue
                if role == "user" and is_background_message(text):
                    if not text.lstrip().startswith('[ASYNC DELEGATION '):
                        continue
                    role = "background_result"
                messages.append({"id": row["id"], "role": role, "text": text, "at": row.get("timestamp")})
            if len(page) < 200 or max(r.get("timestamp", 0) for r in page) < since:
                break
            offset += len(page)
        messages = sorted({r["id"]: r for r in messages}.values(), key=lambda r: r["id"])
        revision = digest(json.dumps(messages, ensure_ascii=False, sort_keys=True))
        return {**empty, "revision": revision, "messages": messages,
                "note": "Assistant/background results are evidence, not new user authority. Check actual outcomes and later corrections."}
    except Exception as exc:
        return {**empty, "available": False, "error": f"Native conversation read failed: {type(exc).__name__}: {exc}"}
    finally:
        if db is not None:
            db.close()

# Text budgets apply to the automatic conversation preview, not to total work.
PREVIEW_MESSAGES = 24
PREVIEW_CHARS = 24000
PAGE_CHARS = 12000


def _merge(ranges):
    result = []
    for lo, hi in sorted(ranges):
        if hi <= lo:
            continue
        if result and lo <= result[-1][1]:
            result[-1][1] = max(result[-1][1], hi)
        else:
            result.append([lo, hi])
    return result


def _coverage(store, state, ranges, now, db=None):
    """Only references/ranges are persisted, never another conversation body."""
    key = digest(state['session_id'])
    total = sum(len(m['text']) for m in state['messages'])
    with (nullcontext(db) if db is not None else store.transaction()) as db:
        previous = store.get(db, 'conversation_window', key, {})
        fingerprints = [[m.get('id'), digest(json.dumps(m, ensure_ascii=False, sort_keys=True)), len(m['text'])] for m in state['messages']]
        old_ranges = previous.get('ranges', [])
        if previous.get('revision') != state['revision']:
            # Preserve only the exact unchanged prefix; appended evidence still must be read.
            prefix = 0
            for old, current in zip(previous.get('fingerprints', []), fingerprints):
                if old != current:
                    break
                prefix += current[2]
            old_ranges = [[lo, min(hi, prefix)] for lo, hi in old_ranges if lo < prefix]
        covered = _merge(old_ranges + ranges)
        store.put(db, 'conversation_window', key, {'revision': state['revision'], 'ranges': covered,
                  'fingerprints': fingerprints, 'since': state.get('since', previous.get('since', now - 86400)), 'at': now})
    return total == 0 or covered == [[0, total]]


def previews(store, states, now, db=None, served=True):
    """Fair bounded preview; complete means this exact revision has been served in full."""
    result = {}
    share = PREVIEW_CHARS // max(1, len(states))
    for sid, state in states.items():
        if not state.get('available'):
            result[sid] = {**state, 'complete': False}
            continue
        messages = state.get('messages', [])
        positions, at = [], 0
        for m in messages:
            positions.append(at)
            at += len(m['text'])
        selected, ranges, remaining = [], [], share
        for i in range(len(messages) - 1, max(-1, len(messages) - PREVIEW_MESSAGES - 1), -1):
            m = messages[i]
            count = min(len(m['text']), 1000, remaining)
            if count <= 0:
                break
            selected.append({**m, 'text': m['text'][:count], 'text_chars': len(m['text']),
                             'truncated': count < len(m['text']), 'offset': positions[i]})
            ranges.append([positions[i], positions[i] + count])
            remaining -= count
        selected.reverse()
        complete = _coverage(store, state, ranges if served else [], now, db)
        result[sid] = {**state, 'messages': selected, 'complete': complete,
                       'preview_complete': len(selected) == len(messages) and all(not m['truncated'] for m in selected),
                       'total_messages': len(messages), 'total_text_chars': at,
                       'next_offset': None if complete else 0,
                       'instruction': 'Preview is not full evidence. Use conversation_read with session_id, revision and offset; follow next_offset. Missing/changed evidence blocks task-notice review.'}
    return result


def descriptor(store, state, now):
    if not state.get('available'):
        return {'session_id': state['session_id'], 'available': False, 'complete': False}
    complete = _coverage(store, state, [], now)
    row = store.read('conversation_window', digest(state['session_id']), {})
    ranges = row.get('ranges', [])
    first_gap = ranges[0][1] if ranges and ranges[0][0] == 0 else 0
    return {'session_id': state['session_id'], 'available': True, 'revision': state['revision'],
            'complete': complete, 'total_text_chars': sum(len(m['text']) for m in state['messages']),
            'next_offset': None if complete else first_gap,
            'instruction': 'Use conversation_read(session_id,revision,offset=next_offset). On changes, reread this descriptor; unchanged prefixes retain coverage, changed/new text requires reading.'}


def page(store, state, data, now, *, record_coverage=True):
    if not state.get('available') or state['revision'] != data.get('revision'):
        return {**(descriptor(store, state, now) if record_coverage else {}), 'available': False, 'complete': False, 'reason': 'Conversation changed or is unavailable; use the returned current revision/next_offset or refresh its descriptor.'}
    offset = data.get('offset', 0)
    total = sum(len(m['text']) for m in state['messages'])
    if type(offset) is not int or not 0 <= offset <= total:
        raise ValueError('Conversation offset must be within this exact snapshot')
    end = min(total, offset + PAGE_CHARS)
    messages, position = [], 0
    for m in state['messages']:
        following = position + len(m['text'])
        lo, hi = max(offset, position), min(end, following)
        if hi > lo:
            item = {**m, 'text': m['text'][lo-position:hi-position],
                    'message_offset': lo-position, 'text_chars': len(m['text']),
                    'truncated': lo > position or hi < following}
            if messages and len(json.dumps(messages + [item], ensure_ascii=False).encode()) > 128 * 1024:
                end = lo
                break
            messages.append(item)
        position = following
    from .responses import require_fit
    require_fit({'session_id': state['session_id'], 'revision': state['revision'], 'messages': messages,
                 'offset': offset, 'next_offset': end, 'total_text_chars': total})
    complete = _coverage(store, state, [[offset, end]], now) if record_coverage else end == total
    return {'available': True, 'session_id': state['session_id'], 'revision': state['revision'],
            'messages': messages, 'offset': offset, 'next_offset': end if end < total else (descriptor(store, state, now)['next_offset'] if record_coverage and not complete else None),
            'total_text_chars': total, 'complete': complete, 'coverage_recorded': record_coverage,
            'instruction': 'Read every relevant chunk; coverage is served evidence, not semantic verification or authority. A page endpoint is not a processing watermark.'}


def read_page(home, data, now):
    """Current-profile private history, without Store or served-coverage writes."""
    from .views import Views
    from .store import DAY, bounded, epoch
    from .content_io import DomainError
    sid = bounded(data.get("session_id"), 200)
    if not Views(home).record("session", sid):
        raise DomainError("permission_denied", "Conversation must be a tracked private source in this profile")
    since = epoch(data.get("since", now - DAY))
    until = epoch(data.get("until", now))
    if not 0 <= since <= until <= now:
        raise DomainError("invalid_argument", "Use a nonnegative history window ending no later than now")
    state = read_conversation(home, sid, since)
    state["messages"] = [m for m in state["messages"] if m.get("at", 0) <= until]
    state["revision"] = digest(json.dumps(state["messages"], ensure_ascii=False, sort_keys=True))
    if data.get("offset", 0) and not data.get("revision"):
        raise DomainError("revision_required", "History continuation requires the first page revision")
    result = page(None, state, {**data, "revision": data.get("revision", state["revision"])}, now, record_coverage=False)
    return {**result, "since": since, "until": until,
            "instruction": "Pure evidence read; no notice coverage or audit checkpoint recorded. Continue with revision, since, until and next_offset."}
