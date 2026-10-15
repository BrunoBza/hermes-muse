"""Transport limits at the tool boundary; receipts use the existing profile store."""
from contextvars import ContextVar
import json

from .content_io import DomainError

LIMIT = 256 * 1024
ARCHIVE = ContextVar('muse_response_archive', default=None)


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def preflight(args):
    if not isinstance(args, dict) or set(args) - {'action', 'data'}:
        raise DomainError('invalid_argument', 'Use action and data only')
    # Bound both structural work and serialized bytes before any journal/track/bind.
    def walk(value, depth=0):
        if depth > 24:
            raise DomainError('size_limit', 'Request nesting exceeds 24 levels')
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str) or len(key) > 128:
                    raise DomainError('invalid_argument', 'Object field names must be text of at most 128 characters')
                walk(child, depth+1)
        elif isinstance(value, list):
            for child in value:
                walk(child, depth+1)
    walk(args)
    if len(encode(args).encode()) > 512 * 1024:
        raise DomainError('size_limit', 'Request exceeds 512 KiB; split unstarted work')
    from .contracts import validate
    validate(args.get('action'), args.get('data', {}))


def require_fit(result):
    """Coverage cannot be recorded for body text that will not reach the caller."""
    if len(encode({'ok': True, 'result': result}).encode()) > LIMIT - 2048:
        raise DomainError('size_limit', 'Evidence page exceeds response budget; no served coverage recorded')


def archive(store, session_id, action, envelope):
    from .store import digest
    from .views import Views
    raw = encode(envelope)
    key = digest(encode([session_id, action, raw]))
    store.write('tool_result', key, {'id': key, 'session_id': session_id, 'action': action, 'body': raw})
    ref = {'action': 'content_read', 'data': {'kind': 'tool_result', 'id': key, 'scope_token': Views(store.home).scope()}}
    if envelope.get('ok'):
        return {'ok': True, 'result': {'result_is_reference': True, 'content_ref': ref,
                'instruction': 'This call completed. Read the exact result in pages; do not repeat its side effects. Unknown native execution is not success or permission to redispatch.'}}
    return {'ok': False, 'code': str(envelope.get('code', 'invalid_argument'))[:128],
            'error': str(envelope.get('error', 'Tool failed'))[:2000], 'error_truncated': True,
            'error_ref': ref, 'retryable': False,
            'instruction': 'Read the complete error before recovery. Do not retry an unknown external execution.'}


def invoke_once(runtime, args, kwargs, callback):
    """Use the existing request journal; never hold its lock across native work."""
    from .contracts import REPLAY_ACTIONS
    data, action = args.get('data', {}), args['action']
    if action not in REPLAY_ACTIONS or not data.get('request_id'):
        return callback()
    from agent.delegation_context import is_delegated_child_context
    from .runtime import private_session, session_info
    if is_delegated_child_context() or not private_session(session_info()) or not kwargs.get('session_id'):
        raise DomainError('permission_denied', 'Replayable state changes require a private originating parent session')
    from .views import Views, canonical
    from .content_io import revision
    from .host import file_lock
    scope = Views(runtime.home).scope()
    key = revision(canonical([scope, action, data['request_id']]))
    signature = revision(canonical([kwargs['session_id'], data]))
    store = runtime.store
    with file_lock(store.path('mutations.lock')):
        old = store.read('mutation_request', key)
        if old:
            if old['signature'] != signature:
                raise DomainError('idempotency_conflict', 'request_id arguments or originating session changed')
            if old.get('result') is None:
                raise DomainError('outcome_unknown', 'Original call is pending/interrupted. Inspect native evidence; do not redispatch with another key')
            return runtime._receipt(old['result'], action=action, data=data)
        intent = {'signature': signature, 'state': 'pending', 'action': action}
        store.write('mutation_request', key, intent)
    raw = callback()
    # callback is the common final-envelope path, including bounded native errors.
    with file_lock(store.path('mutations.lock')):
        store.write('mutation_request', key, {**intent, 'state': 'complete', 'result': json.loads(raw)})
    return raw
