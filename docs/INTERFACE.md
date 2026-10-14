# Muse tool interface

One registered tool, `muse_manage(action, data)`, with 41 actions. Models never supply home/profile/path or host correlation IDs (conversation_read session_id is a read reference, not caller identity). Unknown fields are rejected. Request budget is 512 KiB; response budget is 256 KiB. Native memory/skills/connectors keep their own tools.

| Action | Data fields | Concurrency |
|---|---|---|
| `context` | `` | Action-specific token/revision or pure read |
| `status` | `` | Action-specific token/revision or pure read |
| `conversation_read` | `session_id revision offset` | Action-specific token/revision or pure read |
| `content_read` | `kind id resource scope_token offset length revision cursor limit topic query` | Action-specific token/revision or pure read |
| `content_write` | `kind id resource scope_token body expected_revision request_id signal_id` | Action-specific token/revision or pure read |
| `memory_feedback_review` | `receipt_id decision reason expected_revision request_id` | Action-specific token/revision or pure read |
| `installation_prepare` | `operation signal_id expected_revision request_id` | Action-specific token/revision or pure read |
| `goal_create` | `signal_id title description completion_criteria id parent_id deadline external_ref request_id expected_revision scope_token` | Request key + natural/event key |
| `goal_update` | `id progress status research_review_at signal_id outcome_evidence external_status_verified description completion_criteria evidence_refs expected_revision request_id scope_token` | Required revision + request key |
| `interest_record` | `signal_id title id expires rationale request_id expected_revision scope_token` | Request key + natural/event key |
| `idea_add` | `title rationale goal_id sources expires request_id expected_revision scope_token` | Request key + natural/event key |
| `feedback` | `kind id action signal_id until expected_revision request_id scope_token` | Required revision + request key |
| `preferences` | `start_hour end_hour ordinary_per_day time_sensitive_per_day blocked_topics feed_brief signal_id expected_revision request_id scope_token` | Required revision + request key |
| `notification_add` | `event_key message rationale sources verified_at expires goal_id interest_id priority priority_reason issue_key source_snapshot supersedes signal_id watch_id final_result request_id expected_revision scope_token` | Request key + natural/event key |
| `notification_refresh` | `id verified_at sources message priority priority_reason source_snapshot expected_revision request_id scope_token` | Required revision + request key |
| `notification_review` | `id conversation_revisions verdict reason expected_revision request_id scope_token` | Required revision + request key |
| `notification_resolve` | `id verified_at sources reason expected_revision request_id scope_token` | Required revision + request key |
| `notification_prepare` | `id` | Action-specific token/revision or pure read |
| `notification_queue` | `id` | Action-specific token/revision or pure read |
| `notification_handoff` | `id` | Action-specific token/revision or pure read |
| `watch_create` | `goal_id signal_id schedule prompt stop_condition expires request_id expected_revision scope_token` | Request key + natural/event key |
| `watch_stop` | `job_id` | Action-specific token/revision or pure read |
| `feed_add` | `event_key title content sources why goal_id interest_id request_id expected_revision scope_token` | Request key + natural/event key |
| `feed_list` | `query topic cursor limit scope_token` | Action-specific token/revision or pure read |
| `feed_update` | `id signal_id feedback position delete title content sources expected_revision request_id scope_token` | Required revision + request key |
| `calendar_window` | `mode` | Action-specific token/revision or pure read |
| `calendar_view` | `window sources discovery_complete` | Action-specific token/revision or pure read |
| `source_check` | `source started_at status scope summary expected_resources checked_resources cursor query_window observed_at source_id alias_reason expected_revision request_id scope_token` | Required revision + request key |
| `operations_read` | `through` | Action-specific token/revision or pure read |
| `operations_batch` | `` | Action-specific token/revision or pure read |
| `operations_evidence` | `receipt ref offset length` | Action-specific token/revision or pure read |
| `operations_complete` | `token summary` | Action-specific token/revision or pure read |
| `operations_commit` | `batch reviews` | Action-specific token/revision or pure read |
| `finding_record` | `id evidence summary impact status verification disclosure no_notice_reason expected_revision request_id scope_token` | Required revision + request key |
| `review_complete` | `job up_to through summary goal_id stop_condition source_check_ids` | Action-specific token/revision or pure read |
| `run_complete` | `outcome summary gaps` | Action-specific token/revision or pure read |
| `delegate` | `goal_id goal tasks context output_schema images action subagent_id message` | Action-specific token/revision or pure read |
| `research_start` | `items goal_id context` | Action-specific token/revision or pure read |
| `research_status` | `id` | Action-specific token/revision or pure read |
| `forget` | `kind object_kind id resource signal_id external_status_verified expected_revision request_id scope_token` | Required revision + request key |
| `followup_update` | `kind goal_id candidate_id receipt_id reply_id notice_id expected_revision expected_fingerprint signal_id source_quote offset disposition reason next_action sources goal_ids execution_state result_state summary verified_at external_status_verified evidence_refs retry_failed_notice_id` | Action-specific token/revision or pure read |

See [content access](../skills/companion/references/content.md) for kinds, resource mapping and recovery. The notification prepare/queue/handoff aliases share the same implementation. `content_read` and UI never construct Store or Runtime; context/status do refresh/reconcile and must not be used for UI GET.
