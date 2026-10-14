"""Single-tool field contracts, independent from prompts and UI."""

from .content_io import DomainError

FIELDS = {
    "context": "",
    "status": "",
    "conversation_read": "session_id revision offset read_only since until",
    "content_read": "kind id resource scope_token offset length revision cursor limit topic query",
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
    "review_complete": "job up_to through summary goal_id stop_condition source_check_ids",
    "run_complete": "outcome summary gaps",
    "delegate": "goal_id goal tasks context output_schema images action subagent_id message",
    "research_start": "items goal_id context",
    "research_status": "id",
    "forget": "kind object_kind id resource signal_id external_status_verified",
    "followup_update": "kind goal_id candidate_id receipt_id reply_id notice_id expected_revision expected_fingerprint signal_id source_quote offset disposition reason next_action sources goal_ids execution_state result_state summary verified_at external_status_verified evidence_refs retry_failed_notice_id",
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


def validate(action, data):
    if action not in FIELDS or not isinstance(data, dict):
        raise DomainError("invalid_argument", "Unknown action or invalid data object")
    allowed = set(FIELDS[action].split())
    if action in CAS or action in CREATES:
        allowed |= {"expected_revision", "request_id", "scope_token"}
    unknown = set(data) - allowed
    if unknown:
        raise DomainError(
            "invalid_argument", "Unsupported fields: " + ", ".join(sorted(unknown))
        )
    for name, value in data.items():
        if name in {"offset", "length", "limit", "batch"} and type(value) is not int:
            raise DomainError("invalid_argument", name + " must be an integer")
        if (
            name in {"delete", "external_status_verified", "final_result", "read_only"}
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
                    "receipt_id",
                }
            )
            and value is not None
            and not isinstance(value, str)
        ):
            raise DomainError("invalid_argument", name + " must be text")
    if action in CAS or action in CREATES:
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
