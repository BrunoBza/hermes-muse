"""Single-tool field contracts, independent from prompts and UI."""

from .content_io import DomainError

FIELDS = {
    "context": "section job window cursor limit id offset length revision scope_token part",
    "status": "section job window cursor limit id offset length revision scope_token part",
    "conversation_read": "session_id revision offset read_only since until descriptor",
    "content_read": "kind id resource scope_token offset length revision cursor limit topic query part",
    "content_write": "kind id resource scope_token body expected_revision request_id signal_id",
    "memory_feedback_review": "receipt_id decision reason expected_revision request_id",
    "installation_prepare": "operation signal_id expected_revision request_id",
    "goal_create": "signal_id title description completion_criteria id parent_id deadline external_ref",
    "goal_update": "id progress status research_review_at signal_id outcome_evidence external_status_verified description completion_criteria evidence_refs",
    "interest_record": "signal_id title id expires rationale",
    "idea_add": "title rationale goal_id sources expires",
    "feedback": "kind id action signal_id until",
    "preferences": "start_hour end_hour ordinary_per_day time_sensitive_per_day blocked_topics feed_brief signal_id",
    "notification_add": "event_key message rationale sources verified_at expires goal_id interest_id priority priority_reason issue_key source_snapshot supersedes signal_id watch_id final_result",
    "notification_refresh": "id verified_at sources message priority priority_reason source_snapshot",
    "notification_review": "id conversation_revisions verdict reason",
    "notification_resolve": "id verified_at sources reason",
    "notification_prepare": "id",
    "notification_queue": "id",
    "notification_handoff": "id",
    "watch_create": "goal_id signal_id schedule prompt stop_condition expires",
    "watch_stop": "job_id",
    "feed_add": "event_key title content sources why goal_id interest_id",
    "feed_list": "query topic cursor limit scope_token",
    "feed_update": "id signal_id feedback position delete title content sources",
    "calendar_window": "mode",
    "calendar_view": "window sources discovery_complete",
    "source_check": "source started_at status scope summary expected_resources checked_resources cursor query_window observed_at source_id alias_reason",
    "operations_read": "through",
    "operations_batch": "",
    "operations_evidence": "receipt ref offset length limit session_id job_id since until",
    "operations_complete": "token summary",
    "operations_commit": "batch reviews",
    "finding_record": "id evidence summary impact status verification disclosure no_notice_reason",
    "review_complete": "job up_to through summary goal_id stop_condition source_check_ids window",
    "run_complete": "outcome summary gaps",
    "delegate": "goal_id goal tasks context output_schema images action subagent_id message",
    "research_start": "items goal_id context",
    "research_status": "id",
    "forget": "kind object_kind id resource signal_id external_status_verified",
    "followup_update": "mode object_kind id repair_id cursor scope_token kind goal_id candidate_id receipt_id reply_id notice_id expected_revision expected_fingerprint signal_id source_quote offset snapshot_revision disposition reason next_action sources goal_ids execution_state result_state summary verified_at external_status_verified evidence_refs retry_failed_notice_id",
}
CAS = {
    "goal_update": "goal",
    "preferences": "preferences",
    "feed_update": "feed",
    "feedback": None,
    "notification_refresh": "notice",
    "notification_review": "notice",
    "notification_resolve": "notice",
    "source_check": "source_check",
    "finding_record": "finding",
    "forget": None,
}
CREATES = {
    "goal_create",
    "interest_record",
    "idea_add",
    "notification_add",
    "feed_add",
    "watch_create",
}


# Optional replay keys for actions without an existing object/content journal.
REPLAY_ACTIONS = {'delegate', 'research_start', 'research_status', 'watch_stop',
                  'operations_read', 'operations_batch', 'operations_complete', 'operations_commit',
                  'review_complete', 'run_complete', 'notification_prepare', 'notification_queue',
                  'notification_handoff', 'followup_update'}


def validate(action, data):
    if action not in FIELDS or not isinstance(data, dict):
        raise DomainError("invalid_argument", "Unknown action or invalid data object")
    allowed = set(FIELDS[action].split())
    if action in CAS or action in CREATES:
        allowed |= {"expected_revision", "request_id", "scope_token"}
    if action in REPLAY_ACTIONS:
        allowed.add("request_id")
    unknown = set(data) - allowed
    if unknown:
        raise DomainError(
            "invalid_argument", "Unsupported fields: " + ", ".join(sorted(unknown)[:8]) + (" (and more; all rejected)" if len(unknown) > 8 else "")
        )
    if action == 'followup_update' and data.get('kind') == 'reconcile':
        if data.get('mode', 'dry_run') not in {'dry_run', 'apply', 'rollback'}:
            raise DomainError('invalid_argument', 'Use dry_run/apply/rollback')
        if data.get('mode') in {'apply', 'rollback'} and (not data.get('request_id') or not data.get('expected_revision')):
            raise DomainError('revision_required', 'Reconciliation writes require request_id and expected_revision from dry-run')
    if action in {'context', 'status', 'review_complete'} and 'window' in data and not isinstance(data['window'], str):
        raise DomainError('invalid_argument', 'window must be text')
    if action in {'context', 'status', 'content_read'} and 'cursor' in data and not isinstance(data['cursor'], str):
        raise DomainError('invalid_argument', 'cursor must be text')
    if action == 'content_write' and isinstance(data.get('body'), str):
        if len(data['body']) > 60000 or len(data['body'].encode()) > 256 * 1024:
            raise DomainError('size_limit', 'body exceeds 60000 characters/256 KiB')
    bounds = {'watch_create': {'prompt': 4000, 'stop_condition': 4000},
              'research_start': {'context': 8000}}
    common = {'title': 300, 'description': 8000, 'completion_criteria': 8000,
              'summary': 4000 if action == 'finding_record' else 2000,
              'reason': 2000, 'rationale': 2000, 'why': 2000, 'feedback': 2000,
              'progress': 2000, 'next_action': 2000, 'source_quote': 2000,
              'event_key': 500, 'issue_key': 500, 'priority_reason': 2000,
              'content': 60000, 'feed_brief': 12000, 'alias_reason': 1000}
    if action == 'goal_create':
        common['title'] = 200
    if action in {'notification_add', 'notification_refresh'}:
        common['message'] = 6000
    if action == 'source_check':
        common.update(scope=1000, cursor=4000)
    for name, maximum in {**common, **bounds.get(action, {})}.items():
        if isinstance(data.get(name), str) and len(data[name]) > maximum:
            raise DomainError('size_limit', name + ' exceeds its action budget')
    if action == 'research_start' and isinstance(data.get('items'), list):
        if not 1 <= len(data['items']) <= 24 or any(not isinstance(x, str) or len(x) > 2000 for x in data['items']):
            raise DomainError('size_limit', 'research items require 1..24 text questions of at most 2000 characters')
    if action == 'review_complete' and 'window' in data and data.get('job') not in {'memory-upkeep', 'nightly-review'}:
        raise DomainError('invalid_argument', 'window is only valid for memory-upkeep/nightly-review')
    for name in ('window', 'revision', 'expected_revision', 'snapshot_revision', 'scope_token', 'request_id'):
        if isinstance(data.get(name), str) and len(data[name]) > (128 if name == 'request_id' else 1024):
            raise DomainError('size_limit', name + ' exceeds its token budget')
    if action in {'context', 'status', 'content_read', 'feed_list'} and isinstance(data.get('cursor'), str) and len(data['cursor']) > 2048:
        raise DomainError('size_limit', 'cursor exceeds its token budget')
    for name, value in data.items():
        if (name.endswith('_id') or name in {'id', 'kind', 'section', 'job', 'resource'}) and isinstance(value, str) and len(value) > 512:
            raise DomainError('size_limit', name + ' exceeds its identity budget')
        if name in {"offset", "length", "limit", "batch"} and type(value) is not int:
            raise DomainError("invalid_argument", name + " must be an integer")
        if (
            name in {"delete", "external_status_verified", "final_result", "read_only", "descriptor"}
            and type(value) is not bool
        ):
            raise DomainError("invalid_argument", name + " must be boolean")
        if name in {
            "sources",
            "evidence_refs",
            "blocked_topics",
            "items",
            "reviews",
            "tasks",
            "gaps",
            "source_check_ids",
        } and not isinstance(value, list):
            raise DomainError("invalid_argument", name + " must be an array")
        if (
            (
                name.endswith("_id")
                or name
                in {
                    "id",
                    "kind",
                    "scope_token",
                    "request_id",
                    "signal_id",
                    "resource",
                    "body",
                    "title",
                    "description",
                    "completion_criteria",
                    "query",
                    "topic",
                    "receipt_id", "section", "revision", "snapshot_revision", "part",
                }
            )
            and value is not None
            and not isinstance(value, str)
        ):
            raise DomainError("invalid_argument", name + " must be text")
    if action in CAS or action in CREATES or "request_id" in data:
        if (
            not isinstance(data.get("request_id"), str)
            or not 1 <= len(data["request_id"]) <= 128
        ):
            raise DomainError(
                "invalid_argument", "request_id required (1..128 characters)"
            )
    if action in CAS and "expected_revision" not in data:
        raise DomainError(
            "revision_required", "Read the object through content_read before updating"
        )
