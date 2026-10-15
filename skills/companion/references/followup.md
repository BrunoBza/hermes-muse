# Follow accepted work through real execution and handoff

Load communication for user-facing results, especially its user-handoff guidance when a real blocker requires the user. Keep existing permissions, quiet time and source sweeps. This procedure grants no new authorization.

## Automatic entrypoints

The native pre_llm_call prologue captures eligible real user turns and injects a bounded followup snapshot into this turn's user-message context. post_llm_call records final-response evidence after the tool loop; it cannot continue that loop. Interrupted turns remain pending. Internal results never create a user signal. The existing proactive/hourly/nightly scripts supply the same selector automatically; no extra Cron or model timer is created.

Pending turns are review candidates, NOT goals. Use original user and assistant evidence to decide whether a promise was accepted, fulfilled, cancelled, ambiguous or just chat. Keywords cannot authorize work. Never create a goal merely because a background result, old memory or assistant proposal suggests one.

Use muse_manage action followup_update with data below. IDs/revisions come from the injected snapshot or the goal's managed metadata. Do not hand-edit state or invent receipts.

## Reviewing a missed registration

- kind=evidence, candidate_id: fetch original source text and an exact native assistant match. Missing/ambiguous evidence is explicit; use focused native retrieval if available. kind=evidence, reply_id fetches an actual final-response reference; it is not user authority.
- kind=review, candidate_id, expected_revision, disposition, reason, goal_ids?:
  disposition is no_commitment, already_fulfilled, needs_clarification or link_existing. Explicitly review even if the previous assistant omitted every registration tool.
- To accept missed work, first goal_create with that candidate's ORIGINAL signal_id and actual accepted scope/criteria; then link_existing with the created goal_ids. Code rejects changed source, other-session/source goals, truncated source and expired signal.
- The original real signal must still satisfy the 24h gate. A new unrelated signal cannot renew it. Expired/missing authority needs a specific user clarification, never a fabricated fresh signal. Already accepted goals may continue across days without renewal.
- A review before the final answer is not a review of promises subsequently made in that answer: post captures the actual response and makes the turn pending again.
- kind=due, offset? reads further metadata pages. Counts/partial_selection reveal omitted references; use a finite pass and resume within the existing job budget. Unknown/blocker items are not permission to retry.

## Accepted goals and native receipts

New goals have optional followup v1 metadata. Legacy goals without it are NOT auto-activated. Root status stays active/completed/cancelled; followup execution, business result and delivery are separate.

kind=evidence, goal_id returns current managed metadata and its file fingerprint. To opt an unchanged active legacy goal into follow-through, kind=adopt requires that fingerprint, the current real signal_id and source_quote (at least eight characters from that input) explicitly accepting its unchanged scope. Cron, old recall and expired signals cannot adopt it. This preserves criteria and records the previous source; it does not reactivate cancelled work.

Prefer research_start with goal_id, or delegate with goal_id alongside its native goal/context/tasks. The plugin persists intent before the call and binds its actual native receipt. Native tool controls retain their real handles; do not attach a launch goal_id to a stop/list call. A repeated start for an existing attempt is refused, including after a crash.

For direct native delegate_task only, kind=intent, goal_id, expected_revision, tool="delegate_task" prepares a correlation reference. Put the returned literal [Muse followup intent:ID] in the native context; the pre/post tool hooks bind that actual call. Do not guess a tool_call_id. Do not use a marker from a different session/goal. Orphan receipts grant no authority. kind=bind_receipt, goal_id, expected_revision, receipt_id only links a verified orphan from that goal's exact ORIGINAL user turn/session; it does not dispatch anything.

kind=observe, goal_id, expected_revision reads the exact native delegation. A missing callback is recovered by this action from the existing due tick, not by repeated start. If the handle was lost after provider acceptance, a bounded read-only native journal lookup uses this exact session, time boundary and plugin intent marker. Unsupported schema, pruning, more than 25 candidates or nonunique matches remain unknown. No whole-history scan. Native getter initialization is distinct from the pure read-only due selector.

kind=evidence, receipt_id reads only the exact native tool message identified by that receipt's session and tool_call_id. Follow next_offset for bounded text pages; complete means the exact record was located, not that a truncated page is the whole result or that its business outcome succeeded.

Normal callbacks take priority. Missing callbacks use the existing tick with 30m, 2h, then 8h checks. No change means no user notice. After a day without a new terminal outcome the fallback pauses for review; a real user/owner event may request another read. Do not repeatedly probe a review blocker from Cron. A long consolidating owner can remain active; provide current evidence/ETA rather than a success claim.

An existing external tool may expose owner-level lifecycle without a verifiable per-attempt receipt. Preserve its references through external_ref and the original authorized tool; owner-level idle/completed is not this attempt's business result. Arbitrary terminal stdout/exit0 is never parsed into a remote owner. Do not install another provider, create another session or replace the original owner as recovery.

## Verification, continuation and user blockers

- kind=verification, goal_id, expected_revision, result_state="verified"|"failed", sources, verified_at, summary: read actual current artifacts/results against original completion criteria first. Native running/unknown is not a verified terminal result. Structured child failure cannot be marked successful even if the coordinator or wrapper exited 0. Historical failure text inside a report is not itself a current structured failure.
- Goals with external_ref also require external_status_verified=true after their actual authoritative owner/tool read-back. This is an evidence assertion, not a new external adapter or permission.
- Coordinator completion is one phase. If accepted criteria still need work, do not mark verified. kind=advance with goal_id, expected_revision, sources and next_action records a read-back of a known terminal phase, clears its live intent, and permits the next step WITHIN the same accepted criteria. It refuses running/unknown work and refuses expanding an already verified result into a new scope. Read back any previous external write before advancing; never repeat unknown effects.
- kind=block, goal_id, expected_revision, execution_state="needs_user"|"paused"|"outcome_unknown", reason: preserve the exact blocker. paused also needs signal_id from real current user direction. No automatic identity/password/permission/network/service changes.
- When the user supplies the missing consent/decision, kind=resume with goal_id, expected_revision, signal_id requires the current real input in the source session. It records eligibility, not a provider restart or permission expansion. Re-read existing owner effects before any next attempt.
- New input not yet semantically reviewed holds background actions for its source session. Review it before continuing. Cancel only the requested independent goal/subgoal with goal_update; late receipts cannot reopen its generation. A cancelled intent does not stop an already submitted external action. Use actual supported native stop controls when authorized and report stop_requested until confirmed.

When blocked, use communication's single authoritative user-handoff paragraph. Finish independent authorized preparation first; provide the actual host/UI/verified command or button, user action, reason the assistant cannot complete it, success sign and where work resumes. Web login and CLI identity/workspace are separate. Secrets stay in secure UI/vault.

## Final user delivery

A generated final response, verified artifact, candidate, queued notice, native transport receipt and user reading are different events.

After verification, inspect the source conversation/reply_refs before sending a duplicate. kind=handoff, goal_id, expected_revision, reply_id, reason links an actual final-response fact after the original request (possibly before the later formal verification) and retains delivery_state=unknown: this host has no universal transport proof for ordinary replies. It prevents automatically queueing another final-result notice for the same unknown outcome; it is NOT a claim of delivery. The model must judge whether the actual reply satisfies the original result.

For asynchronous results, retain the existing notification_add/review/prepare flow and its authority/quiet-time/dedup/budget rules. Use final_result only for this accepted verified result; no automatic promised/urgent promotion. kind=handoff, goal_id, expected_revision, notice_id links that exact final-result notice. It remains prepared/queued/unknown until host.reconcile reads its actual native execution-specific receipt. A later handoff can confirm that exact settled notice; queued is not sent and confirmed is not read. Never create a replacement notice or change channels for unknown delivery.

Followup uses profile-local existing records and managed GOAL.md; not a second task board. CAS and file fingerprint checks reject stale writes/user edits. Forgetting a goal cleans its intent/receipt/review references and leaves no-replay tombstones; native history/artifacts/backups still require the existing explicit cleanup procedure. No automatic historical activation, source-watermark advancement, calendar write or extra Cron is introduced.

## Recover a large backlog

Use followup_update(kind=due,offset=0); enumerate all next_offset pages with the returned snapshot_revision before changing entries. A changed selection returns revision_conflict: restart the index, deduplicate collected IDs, and re-read each object's current revision before acting. Orphans have their own total and are included even when due/turn counts are zero. An orphan/queued/dispatched record is not proof of active work or failed delivery. Resolve exact existing owners and replies; never relaunch an unknown execution, promote unknown to confirmed, or clear old receipts as a recovery shortcut. Inspect one bounded group, save verified progress, then enumerate the remaining backlog again.


## Evidence convergence and historical repair

Completion callbacks (including Cron parents), native session-end hooks and existing owned-maintenance overview reads now converge existing evidence, without dispatch, polling or sending. Maintenance advances a bounded in-process lexical cursor (25 objects per overview); restarts safely restart the scan. Native durable rows take precedence; if pruned, the host-owned aggregate live manifest can prove all child statuses terminal. A text callback/transcript sentence cannot prove success. completed/interrupted/failed remain distinct; terminal receipts remain readable but leave the unresolved orphan count. unknown/missing stays unresolved, and terminal execution never verifies business criteria.

An exact persisted original-session reply matching the current verified result/artifact can form a `recorded_unconfirmed` handoff basis automatically. It remains delivery_state=unknown, not confirmed/read, and suppresses redundant handling. Missing row IDs may be recovered only by a unique full-text hash in that session; ambiguous/unrelated/older-version replies cannot settle a goal. Narrow answered status/factual questions with no accepted goal/delegation or future promise can settle as no_commitment at session end. Ambiguous requests, interrupted/failed turns and explicitly needs_clarification turns still require semantic review. Ordinary questions do not create goals.

Use the existing `muse_manage(action="followup_update")` with `kind="reconcile"`:

1. `mode="dry_run"` (default), optional `cursor`, `scope_token`: pure read, at most ten object descriptors. Follow next_cursor until null. Lexical keys are live, not an immutable snapshot: concurrent earlier inserts need a fresh pass; no pages are marked served/reviewed. No profile/home parameter is accepted.
2. For a `change=true` item, `mode="apply", object_kind, id, expected_revision, scope_token, request_id`. Copy the opaque expected_revision. The plugin rechecks native evidence under the existing mutation lock. It writes a durable preimage to existing records/followup_repair BEFORE changing one object; result returns repair_id and current revision. No separate DB or arbitrary state patch. Same request_id/arguments replay exactly. A stale object requires dry-run again; unknown external work is never dispatched.
3. `mode="rollback", repair_id, expected_revision, request_id, scope_token`: restore that preimage only if current metadata still matches the repair's after-image; otherwise reject. Goal bodies and unrelated files are preserved, not restored from old snapshots. Repair IDs are listed in dry-run for crash recovery. Back up the installation/data consistently before an operator applies a historical batch; do not restore a whole old DB over new activity. Future hooks may rederive the same justified convergence after rollback; rollback does not erase native evidence.

These writes stay parent-only and profile-scoped. A cancelled goal never reopens. A normally running recurring Cron is not proof of a one-off goal's completion or delegation ownership: no name-based linking. Explicit verification/ownership is still needed for those legacy goals. The diagnostic endpoint is not permission to apply production repairs; follow the user's deployment/repair authorization.
