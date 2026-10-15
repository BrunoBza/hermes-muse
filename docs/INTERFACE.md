# Muse tool interface

One registered tool, `muse_manage(action, data)`, with 41 actions. Models never supply home/profile/path or host correlation IDs (conversation_read session_id is a read reference, not caller identity). Unknown fields are rejected. Request budget is 512 KiB; response budget is 256 KiB. Native memory/skills/connectors keep their own tools.

| Action | Data fields | Concurrency |
|---|---|---|
| `context` | `section job window cursor limit id offset length revision scope_token part` | Action-specific token/revision or pure read |
| `status` | `section job window cursor limit id offset length revision scope_token part` | Action-specific token/revision or pure read |
| `conversation_read` | `session_id revision offset read_only since until descriptor` | Action-specific token/revision or pure read |
| `content_read` | `kind id resource scope_token offset length revision cursor limit topic query part` | Action-specific token/revision or pure read |
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
| `operations_evidence` | `receipt ref offset length limit session_id job_id since until` | Action-specific token/revision or pure read |
| `operations_complete` | `token summary` | Action-specific token/revision or pure read |
| `operations_commit` | `batch reviews` | Action-specific token/revision or pure read |
| `finding_record` | `id evidence summary impact status verification disclosure no_notice_reason expected_revision request_id scope_token` | Required revision + request key |
| `review_complete` | `job up_to through summary goal_id stop_condition source_check_ids window` | Action-specific token/revision or pure read |
| `run_complete` | `outcome summary gaps` | Action-specific token/revision or pure read |
| `delegate` | `goal_id goal tasks context output_schema images action subagent_id message` | Action-specific token/revision or pure read |
| `research_start` | `items goal_id context` | Action-specific token/revision or pure read |
| `research_status` | `id` | Action-specific token/revision or pure read |
| `forget` | `kind object_kind id resource signal_id external_status_verified expected_revision request_id scope_token` | Required revision + request key |
| `followup_update` | `kind goal_id candidate_id receipt_id reply_id notice_id expected_revision expected_fingerprint signal_id source_quote offset snapshot_revision disposition reason next_action sources goal_ids execution_state result_state summary verified_at external_status_verified evidence_refs retry_failed_notice_id` | Action-specific token/revision or pure read |

See [content access](../skills/companion/references/content.md) for kinds, resource mapping and recovery. The notification prepare/queue/handoff aliases share the same implementation. `content_read` and UI never construct Store or Runtime; parent context/status bind native maintenance and record explicit review-window/coverage receipts but no longer aggregate/reconcile all notifications; they are not UI GET endpoints. Child projections are pure.

Native children may read content_read/feed_list/operations_evidence/conversation_read/calendar_window/calendar_view within the host profile and private-user boundary. Child context/status return pure paginated projections before track/bind/reconcile. operations_evidence indexes use offset/limit and next_offset; bodies use ref/offset/length. session_id/job_id/since/until narrow saved receipt evidence. conversation_read is always pure for children; parent default retains served coverage, while read_only=true enables pure history with since/until and revision-checked continuation. operations_read/batch and all writes/checkpoints remain parent-only. No model-supplied profile/home or new grant authority.

## Authenticated Dashboard lifecycle

GET /profiles lists native registered profile metadata. POST /profiles/{name} accepts exactly operation=enable|disable, expected_revision and request_id. Default is refused server-side, including remove requests. No delete operation exists. Content GETs accept selected_profile for explicit local selection while host authentication/enablement remains profile=default. Content remains read-only; administration invokes official lifecycle in an isolated profile process. This is not an agent tool or child capability.

Context and review window migration: see [context procedure](../skills/companion/references/context.md). All model signal checkpoints now require its returned window; internal legacy service calls are not the public tool contract. Metadata pages are explicit JSON text chunks, joined before interpretation.

### Final tool response and recovery

Every action validates the whole request (512 KiB, nesting and control-token bounds) before journal, track, bind or dispatch. Oversized content/question/watch input is rejected before work. `window` belongs only to memory-upkeep/nightly-review. The final 256 KiB envelope includes revision/recovery fields and errors.

Committed large results use `result_is_reference/content_ref`; large native errors remain `ok:false` with a bounded reason and `error_ref`. Follow these refs with `content_read`; retain revision and concatenate body pages before interpreting the JSON. `kind=tool_result` is an immutable exact tool envelope in existing profile records, accessible only by its originating private session and ID (no collection or Dashboard exposure). It does not authorize a side effect, certify served conversation evidence, or claim native task completion. Ordinary object references still use their existing domain access. Pure reads do not create receipt records; invalid input is rejected with a bounded explanation.

The following actions additionally accept an optional `request_id` (1..128 characters): delegate, research_start, research_status, watch_stop, operations_read, operations_batch, operations_complete, operations_commit, review_complete, run_complete, notification_prepare, notification_queue, notification_handoff, followup_update. Use it for a logical state-changing call; identical arguments/key return its exact completed receipt. A key with changed arguments/origin is rejected. A pending/interrupted call returns outcome_unknown without repeating work; inspect native evidence or its existing checkpoint, never create a new key to redispatch unknown execution. This reuses mutation_request, releases the lock during native work, and does not replace CAS or existing own content/install journals. Calls without a key retain their existing recovery contract and must not be blindly retried.

`research_start` large results reference the saved research object; `research_status` may reference the exact observed envelope. Both can be fully read via content_read pages without another dispatch. An allocation receipt (operations_read/batch) is not substantive review: read its refs and actual evidence before committing a checkpoint.
