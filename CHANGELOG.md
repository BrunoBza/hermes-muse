# Unreleased — page redesign

- Dashboard/Desktop page: theme-variable styling, shared components, tabs with counts, clickable Feed rows, safe Markdown detail pages with a separate source list, grouped Ideas with an explanatory empty state, and open-first Goals with a folded closed section.
- Read-only list projections: goals `status=open|closed` filter, state/time/latest-progress fields and open-first ordering; ideas `last_review_at`; feed/idea `source_count`.

# 0.3.0 — simple goals (2026-10-16)

- Replace execution/result/delivery followup state machines with active/done/cancelled goals, optional owner handles, short due summaries and one optional integer write revision.
- Breaking: remove followup_update (including rebind/reconcile/repair), orphan receipts, reply-hash handoff checks, newer-input freezes, signal age gates and caller scope_token fields. Use context(section=followups) and parent goal_update instead.
- Archive original 0.2.x goals/records on first load. Back up and stop writers before offline rollback: run python -m hermes_muse.migration --home <profile-home> --rollback using 0.3.0, then restore the prior plugin code. New goal edits refuse rollback; completed cycles remain archived on a later upgrade. Preserve profile/child/Cron boundaries, notification delivery and unknown-write safety.

# 0.2.4 — historical followup rebinding (2026-10-15)

- Enforce exclusive successor ownership from existing goals, retain delivery evidence by rejecting conflicting rebinds, and require strictly later receipt/result timestamps.

- Add parent-only historical reply/successor binding through `followup_update(kind=rebind)` with exact native evidence, CAS, idempotency and repair preimages/conditional rollback.
- Keep original execution receipts and unknown delivery semantics; no dispatch, automatic delivery inference or automatic production migration.

# 0.2.3 — followup evidence convergence (2026-10-15)

- Converge native delegation terminal evidence through existing hooks; retain interrupted/failed distinctions and unknown safety.
- Replay explicitly reviewed original-session handoffs without claiming transport delivery; unreviewed summary/path mentions never prove delivery. Settle only complete literal inquiries from a closed set without goals; arbitrary prefixes/topics and mixed instructions remain pending for explicit review.
- Fail closed on corrupt/conflicting durable evidence. Expose newer-input blockers and support goal-scoped semantic unrelated reviews without hiding older cancellations.
- Add bounded followup reconciliation dry-run, per-object CAS apply/preimage backup and conditional rollback in the existing tool/store.
- Retain current-profile/child protections, cancellation, budgets and no-redispatch behavior. No production migration or deployment implied.
- v0.2.3 is the first public release since 0.1.27; 0.2.0–0.2.2 were developed on the same branch and ship with it.
- State that Windows is not supported for now and drop it from the CI matrix.
- Document the 30-minute floor for new repeating watches and the parent-model default for workers consistently, and add regression tests for the floor, Cron `feed_brief` edits not waking `feed-pulse`, and the unit suite on hosts without Hermes core or with symlinked temp directories.

# 0.2.2 — bounded context and maintenance evidence (2026-10-15)

- Discoverable context/status section pages and frozen, reference-only signal review windows; reject unread checkpoint advances.
- Current conversation descriptors and unchanged-prefix coverage let long evidence reads survive appends without skipping corrections.
- Page oversized object metadata, return reference receipts for oversized committed mutations, and preserve CAS/idempotent replay.
- Fix orphan-only followup continuation, bind pages to selection revision; document existing Feed correction and finding absent creation.
- Align scheduled source coverage with explicit profile duties and optional preference prose; keep the full general-assistant default and all existing execution/delivery safeguards.
- Keep default Dashboard/profile management, child read boundaries, notification budgets and transport semantics. No deployment implied.

# 0.2.1 — unified local profile Dashboard (2026-10-15)

- Full default installation hosts the page; explicit registered-profile selection before content reads.
- Backend-enforced default read-only administration; native install/enable and data-preserving disable for other profiles.
- Reuse owned-task preparation, retain user pauses/cadences, isolate lifecycle processes and credentials, and keep GETs free of initialization.
- Clarify host-dispatched Muse tools with Docker terminal and independent remote Hermes instances. Windows compatibility remains unresolved.

# 0.2.0 — approved implementation (2026-10-15)

- Scoped content tools, explicit CAS/request keys, pure read projections and plugin-owned UI.
- Correlated memory feedback, current audit identities and replayable delivery evidence.
- Explicit installation preparation, public native delegation, conservative watch minimum and Cron wake protection.
- Breaking tool response migration: feed_list returns a paginated object; mutable actions require revision/request keys. See docs/INTERFACE.md.

# Changelog

## 0.1.27 catalog compatibility

Precise soft-inbox retention and instructed-read-only disclosures; Cron watch scheduling policy and explicit 4,000-character fields; native 30-minute default without changing explicit cadences. Conversation previews gain complete revision-checked chunk retrieval and range coverage that gates notices without advancing processing watermarks. Research/audit respect lower user concurrency while retaining every question/page. Public Cron delegation is used for compatible unpinned routes; pinned/unknown parent-routing exceptions remain explicitly unresolved. Includes the previously local 0.1.26 follow-through and calendar/Apple work, without deploying existing installations.


## 0.1.26

- Automatically retain real-turn review candidates and inject bounded due references through the native user-message hook; candidates never grant execution authority.
- Persist accepted-goal native dispatch intent before launch, observe exact receipts, recover a missing handle from a bounded native journal read, and reject unknown relaunches.
- Reuse the six Cron pre-run outputs for recovery/verification/handoff without changing cadence, source sweeps or calendar coverage.
- Separate owner execution, business verification and native notice delivery; add current, concrete user-handoff guidance in communication.
- Preserve legacy goals, user overlays, notification rules, profiles, native identity/memory and prompt-cache history.

## 0.1.25

- Have receiving conversations retrieve original source details when an incomplete handoff prevents a useful judgment, with truthful access failures and unchanged external-write authority.
- Preserve actionable source identities, timestamps and locators in prepared findings.
- Add a provider-neutral briefing procedure for user-subscribed native reports, sharing Muse source and communication rules without adding a fixed Cron or silently adopting existing jobs.

## 0.1.24

- Route Muse Cron worker creation through a plugin entry that inherits the actual parent model and connection; keep ordinary conversation delegation settings unchanged.
- Use the same entry for parallel self-review and direct research workers, joining results within the Cron run. Preserve native reasoning, permission and execution limits.
- Update the existing Skill and prompts; no new Cron jobs, profile configuration changes or state migration.

## 0.1.23

- Batch self-review into disjoint assignments for native parallel workers, keeping raw evidence out of the parent conversation.
- Add scoped evidence indexes and full chunked expansion; retain original intent and linked call results.
- Commit numeric batch/slot results using server-held receipts, advance only contiguous reviewed work, and resume unfinished assignments after interruption.
- Save partial progress before the host iteration budget is exhausted; keep model choice, source coverage and six fixed schedules unchanged.

## 0.1.22

- Mark off-schedule wakes as native manual runs so cron-expression repair does not silently discard quiet-time memory upkeep or Feed preference refreshes. Preserve recurring schedules and user-paused state.

## 0.1.21

- Give operation-review pages independent receipts; preserve evidence during concurrent reads and merge repeated/overlapping completions without losing progress.
- Keep failed tool reads visible while excluding successful Skill/tool-discovery boilerplate from historical audits.
- Assign the shared operation audit to hourly upkeep. Patrol and Feed verify their own work; nightly review writes confirmed alignment without waiting for the backlog.
- Track actual task stages and partial completion separately from native Cron exit status. Require hourly audit completion and fresh nightly artifacts before recording full completion; preserve recovery checkpoints.
- Keep the same six fixed jobs, schedule, source coverage, models and delivery controls.

## 0.1.20

- Teach the existing communication/goals procedures to consider a request’s practical consequences, carry notification/failure/exit rules into actual work, and verify changes before confirming.
- Encourage a natural, warm, candid voice that explains useful judgment without catchphrases, forced humor or a fixed reply template.
- Clarify that frequency/scope changes update the existing native Cron job; watch_create is not an update API. Preserve explicit report subscriptions and user constraints.
- Give existing conversations the procedure pointer and keep the system summary within the host’s prompt budget. No new Skill, prompt file, Cron or state storage.

## 0.1.19

- Make receiving replies understandable without reading internal deliveries: identify the subject and change, then integrate verified findings and practical impact.
- Apply shared receiving guidance to native Cron results in private conversations, including existing non-Muse jobs. Preserve their task definitions and keep generated results out of user signals.

## 0.1.18

- Preserve the review snapshot boundary across pages and return an explicit continuation instruction. Reject substituting the page checkpoint for the snapshot boundary, caught in a real maintenance run.

- Exclude self-review calls routed through Hermes’s native tool_call dispatcher, as well as direct calls. Mixed batches containing actual mutations remain visible. This closes a gap found during Macmini live acceptance of 0.1.17.

## 0.1.17

- Review native tool calls/results and owned Cron outcomes through the existing state tool, including persisted child sessions and late tool results.
- Keep only operation checkpoints, execution/session references and evidence-backed findings in the existing state database; failed reads do not advance the review.
- Add a self-review procedure to the existing Skill and hourly/nightly maintenance: verify actions and repairs, admit consequential mistakes and track actual disclosure.
- Make Bot Chat handoffs explicitly continue the same assistant's work and responsibility, without inventing completed actions or blaming a separate background report.
- Preserve six Cron jobs, existing settings, identity files and native execution history; add no model/provider dependency or automatic rollback.

## 0.1.16

- Include native assistant outcomes and user corrections in patrol context; require a current relevance review before sending and recheck at finalization.
- Group notice revisions by issue and retire superseded unsent candidates while retaining actual delivery history.
- Preserve original-item titles, IDs and due/timezone in notice evidence; do not expand ambiguous names.
- Remove the installation-default one-per-day ordinary limit; retain explicit limits and migrate only untouched defaults.
- Reuse verified tool-call conventions through the existing Skill and TOOLS.md.

## 0.1.15

- Align all job, Skill, system and research instructions around useful depth, initiative, completion and recovery; remove automatic next-pass deferral and rigid review formats.
- Add one shared Bot Chat receiving prompt and a communication procedure. Notices and review reports arrive as internal findings to explain directly to the user, not messages to acknowledge.
- Preserve direct-channel text, delivery checks, user intent boundaries, existing settings and the six recurring jobs; receiving envelopes never become user signals or new reminder loops.

## 0.1.14

- Resolve previously merged source IDs still held by in-flight patrols, so stale context cannot recreate duplicates.

## 0.1.13

- Return remaining review batches directly so hourly/nightly work can finish its snapshot in one run; preserve timestamp ties and truthful partial progress.
- Explain pending notification blockers and earliest eligibility; allow evidence-backed urgency reassessment without bypassing user snoozes or inventing promises.
- Bind verified tool aliases to existing source IDs and archive duplicate observations without transferring success checkpoints.


## 0.1.12

- Preserve all recorded real-user context from the last day for patrols, removing the 0.1.11 eight-message/1,000-character excerpt cap. Earlier context remains available through native memory/session retrieval.
- Make coverage, timely follow-through and user experience the priority; reuse tools and source records only without reducing useful checks or context. The 0.1.11 source, signal and receipt fixes remain.

## 0.1.11

- Exclude native async-completion envelopes from user signals and signal-backed actions. Preserve historical misclassified messages as background audit evidence.
- Derive source IDs from connection/account/resource identity; track expected and checked resources separately. Incomplete coverage cannot advance the successful checkpoint. Archive old free-form source records without guessing their identities.
- Read the native same-profile Bot Chat receipt by its execution-specific key. Repair finalized unknown outcomes when that exact receipt settles, even after later patrols overwrite the latest-job pointer; never resend.
- Give each Cron only its relevant signal context. Patrols reuse tested read recipes, batch independent reads and use source checkpoints while continuing live source inspection on every tick.

## 0.1.10

- Run all six fixed jobs on schedule instead of treating empty local goals/interests as proof there is no work. Patrols discover connected services/devices, inspect changes and upcoming deadlines, then stay silent when nothing merits a notice. This increases scheduled model usage.
- Record per-source coverage and successful watermarks; partial or failed reads preserve the previous successful position. Retire stale unsent notices from verified source evidence.
- Add weather/travel changes, interest news and relevant local opportunities to the existing patrol/Feed procedures, with current context, original sources, expiry and the same attention budget. No extra Cron or service dependency.
- Give nightly review its own signal cursor; keep pending notices visible, fix interest snooze/resumption and a nested SQLite transaction during interest-notice finalization.
- Allow evidence-backed completion of accepted goals across days, verified external cancellation and expiring Ideas without a fabricated goal. New commitments and scope changes still require user evidence.
- Use one native asynchronous coordinator for new research batches, with host result callbacks and durable status. No user-driven wave advancement for new work; legacy batches remain inspectable.
- Keep one Skill, seven prompts, four hooks and six fixed jobs. Preserve user templates, native identity/memory and job schedule/model/pause choices.

## 0.1.9

- Expand proactive behavior instructions: notice concrete conversational plans, prepare useful work before interrupting, select one strongest ordinary item, and avoid status chasing or repeated offers.
- Connect memory, goal research, patrol selection and feedback/expiry rules without new Skills, hooks or Cron jobs. Existing execution and permission checks are unchanged.
- Add natural conversation and evidence-first follow-through guidance, plus bounded working lessons maintained in the companion workspace AGENTS.md during nightly review. Existing user instructions and SOUL are preserved.

## 0.1.8

- Fix the live-acceptance failure in 0.1.7 where the model returned a dispatch-status summary instead of the notice body. A narrowly scoped native transform_llm_output hook now finalizes patrol/watch output from approved records.
- Recheck lifecycle and attention conditions at final output; require that finalization before recognizing a direct notice as sent. Other conversations and review reports are unchanged.
- Registers four hooks; still one Skill, seven prompt files and six fixed Cron jobs. No delivery-only Cron is created.

## 0.1.7

- Deliver selected reminders in the patrol/watch Cron's own final response; no additional delivery-only Cron is created. Deferred candidates remain for the next patrol.
- Keep lifecycle, freshness, deduplication and attention checks; bind native receipts to the exact preparing execution instead of the recurring job's latest run.
- Migrate the old silent patrol and unchanged generated monitoring instructions once; preserve schedules, pauses and user-selected destinations. Existing delivery-only jobs can finish through their original path.

## 0.1.6

- Exclude all native Cron deliveries from user-signal collection, including existing jobs outside Muse. Keeps background results from creating or renewing interests as if the user had spoken. No change to allowed background state operations.
- Resolve macOS temporary-directory aliases in the native integration test.
- Document explicit profile selection, Cron model defaults and the `muse` toolset requirement when platform tool lists are configured.

## 0.1.5

- Add weekly outcome/cost review and monthly instruction/workflow audit, using the shared Skill and current-profile Bot Chat. Reports propose changes, save summaries for follow-up, and exclude a separate Skill audit.

- Rebuild runtime behavior, background prompts and Skill procedures from v0.1.2, then reapply the current-profile Bot Chat delivery changes.
- Remove the 0.1.3 blanket Cron state-write restrictions, the plugin's 30-minute/4000-character watch limits and its extra schedule validator.
- Remove the 0.1.4 read-only restriction on Bot Chat receiving turns. Keep the original user-evidence checks and exclude delivered results from new user signals.
- Retain Bot Chat receipts, exact-notice deduplication and the README's Bot Chat workflow.


## 0.1.4

- Send selected Cron results to the current profile's Bot Chat by default. The bot reads the result and replies in that chat.
- Remove the separate source-session injection step; notification_handoff uses the same delivery queue.
- Track live-owner and deferred Bot Chat receipts, without treating admission as a completed reply.
- Exclude incoming delivery turns from user-signal collection and prevent recursive notification creation.
- Document Bot Chat as the recommended workflow, native missing-chat creation and the installer's static after-install notes.


## 0.1.3

- Refuse user-decision state operations from Cron, including use of saved user signals; keep research progress, reminder preparation and watch stopping available.
- Limit new watch prompts to 4000 characters and recurring clock slots to at least 30 minutes, including midnight. One-off reminders can be sooner.
- Exclude Hermes bot-chat targets from the single-home notification fallback.
- Use Hermes's read-only configuration loader.
- Add real-Hermes regressions for these boundaries and align the Skill/background prompts with them.
- Include the revised bilingual feature comparisons and bundled Skill, prompt and hook documentation.

## 0.1.2

Reorganized both READMEs as a project reference and added feature coverage tables. The tables distinguish implemented code, configured model procedures, partial support and missing features. Runtime behavior is unchanged.

## 0.1.1

Rewrote the English and Chinese READMEs around the project's inspiration from Meta Muse and the everyday follow-up behavior it aims to bring to Hermes. Installation and runtime behavior are unchanged.

## 0.1.0

Initial independent companion assembly: one Skill, four script-gated recurring jobs, five prompts, transactional operational state, goals/subgoals and expiring interests, reminder preparation and native delivery tracking, quiet upkeep, reflection/relationships, silent Feed operations, bounded research, profile-scoped initialization and documented native-remove cleanup. No mandatory external provider or core patch.

### Independent acceptance followup (2026-10-15)

- Restrict installation preparation to a whole, operation-matching Muse command.
- Confine saved feedback to its original turn and invalidate superseded unannounced saves before replay.
- Make audit packages parent-only while trusted child grants are unavailable; reject empty-evidence dispatch.
- Resolve source aliases once through the shared service resolver so CAS protects the actual canonical row.
- Document the unresolved Windows regression; no unsafe fallback or Windows acceptance claim.

### Child evidence and parallel review correction (2026-10-15)

- Allow native children to read current-profile evidence/content without an extra grant service; keep global writes/checkpoints parent-owned.
- Route child context/status and history to pure projections; add paged evidence indexes and time/session/job narrowing.
- Restore executable parallel audit packages and native dispatch, preserving original-owner recovery and contiguous parent commits.
