# Calendar 30-day implementation report

Date: 2026-10-12. Host: mbp.tail6cde6f.ts.net. Checkout: /Users/chiangguantik/code/hermes-muse-calendar-30d. Branch: feature/calendar-30-day. Origin: https://github.com/xiaohei-info/hermes-muse.git.

## Base and delivery status

Original base is e71945c6dd76b19f54dfeb6fedde24a94876e1b5, exactly the requested installed baseline; no upstream delta was incorporated. Work is local, un-deployed, and not a release. No push, PR, publication, deployment, restart, external message, calendar write, live cron-store edit or network configuration change was performed. The pre-existing untracked .serena/ directory is excluded. The coordinator's unrelated installed feed.md change was never accessed or edited.

The scoped local commit and full base-to-HEAD patch are recorded in /Users/chiangguantik/code/hermes-muse-calendar-30d-review.json after committing this report. That JSON also includes any uncommitted scoped patch, test outcomes and exact head SHA. Final native integration and official validation are pending coordinator execution before acceptance/release, as explicitly agreed during implementation.

## Implemented behavior and architecture

- On-demand rolling continuous 30 local days and natural current calendar month through calendar_window/calendar_view on the existing muse_manage tool. context supplies the default rolling query. Half-open overlap boundaries, IANA DST gaps/folds and year/month changes are explicit. Fixed-offset native profiles (including named CST) retain the actual offset with an honest DST limitation, never a guessed zone or UTC fallback.
- Every existing patrol is instructed to read the full 30-day interval and assess useful preparation on days 8–30. The former seven-day calendar default is removed. Longer horizon, unchanged 30-minute cadence and notification selection/lifecycle; no event jobs, new watches or reminder quota.
- Provider-neutral skill discovery covers already enabled authorized Apple/Google/other accounts and all calendar resources. Complete inventory/event page chains, exact query interval and observation lower/upper bounds determine reported coverage. Useful completed pages survive partial failure; empty, partial, error and unavailable stay distinct.
- Original source/calendar names and IDs, event fields/timezones, original all-day dates, cross-zone profile overlays, multi-day schedules, recurring occurrence identities, moved exceptions and cancelled evidence remain available. All-day observances are not automatically conflicts. Daily event/busy/overlap indexes and evidence-backed preparation candidates do not drop supplied detail.
- Conservative exact identity dedup scopes UID/native ID and occurrence identity to connection/account/calendar. Same-title/time distinct events never merge; a recurring series never collapses. Identical same-calendar copies can merge while preserving native copy IDs. Cross-calendar/connector UID copies stay separate; conflicting versions remain visible and mark that resource partial.
- Independent calendars:rolling-30d and calendars:natural-month checkpoints cannot overwrite legacy calendars:all seven-day success. source_check independently rejects query_window/resource mismatches, preserves successful scope/resources/window/observation/cursor on failures, and rejects older starts/older same-query observations.

The minimal executable helper is stateless stdlib code; it performs no I/O, calendar calls, persistent event storage or scheduling. Existing connector tools do authorized reads; the model normalizes actual receipts and performs preparation judgment. The existing transactional source_check action records only coverage metadata after dependent work succeeds. This matches the skill-driven plugin rather than introducing a calendar sync service, DB or UI. Registration remains one Skill and one tool with additional actions. Native core and all existing notice policy code are unchanged.

## Changed paths

- hermes_muse/calendar.py: window, timezone, page/coverage validation, occurrence dedup and daily assembly.
- hermes_muse/service.py: tool action methods, context window, independent successful coverage metadata and resource/race guards.
- hermes_muse/runtime.py: existing tool action enumeration/descriptions and read-only child eligibility.
- skills/companion/references/calendar.md: complete source/read/normalization/display and patrol contract.
- skills/companion/SKILL.md: route calendar requests to that procedure.
- skills/companion/references/proactivity.md: actual 30-day patrol coverage and checkpoint separation.
- skills/companion/references/briefings.md: reuse calendar semantics for requested calendar briefings.
- prompts/proactive-watch.md: require full 30-day calendar reads and advance preparation with existing notice policy.
- README.md and README.zh-CN.md: user-facing behavior and honest limitations.
- docs/DESIGN.md and docs/ACCEPTANCE.md: architecture and synthetic/native/semantic acceptance.
- tests/test_calendar.py: eleven executable synthetic regressions, including Runtime.handle entrypoints.
- tests/native_calendar_smoke.py and tests/native_smoke.py: registered native-tool integration in temporary A/B profiles; no models or real connectors/messages.
- .github/workflows/test.yml: test-only tzdata installation on Windows, no mandatory production dependency.
- docs/calendar-30-day-implementation-report.md: this report.

## Exact commands and observed outcomes

Before changes: `python -m unittest discover -s tests -q` — PASS, 88 tests.

Final scoped tests: `python -m unittest discover -s tests -p test_calendar.py -v` — PASS, 11 tests. Covers rolling/month boundaries, spring/fall DST and gap/fold resolution, fixed-offset CST round-trip, boundary overlap, original all-day dates/cross-zone overlays, multi-day busy/overlap ordering, recurrence moves/cancellations, identical copy versus distinct IDs and cross-calendar copies, day-8/day-30 preparation, pagination/partial errors, stale receipts, old successful watermark preservation, separate legacy/month/rolling checkpoints, concurrent ordering, Runtime.handle/SCHEMA entrypoints and private-session rejection. Expected negative-test log messages are calendar_view missing window and group-session rejection.

Final full suite: `python -m unittest discover -s tests -q` — PASS, 99 tests. Existing notification dedup, budgets, quiet time, lifecycle, receipt handling, runs, audit and profile-isolation regressions pass.

`python -m compileall -q hermes_muse tests` — PASS, exit 0.

`git diff --check` — PASS, exit 0.

`python tests/native_smoke.py` — NOT PASSED remotely, exit 1 before native execution: `ModuleNotFoundError: No module named 'hermes_constants'` at the isolated test's native import. No model or live connector was called. Native calendar assertions are implemented and compiled but await the coordinator's Hermes runtime.

Official validation attempt used a temporary HERMES_HOME:

```python
import os, subprocess, tempfile
with tempfile.TemporaryDirectory(prefix="muse-calendar-validation-") as scratch:
    subprocess.run(["hermes", "plugins", "validate", ".", "--json"],
                   env=dict(os.environ, HERMES_HOME=scratch),
                   text=True, capture_output=True)
```

No validation output was returned; the local hermes shell launcher did not provide a usable immediate validator result. The controlling process was interrupted (exit 130 / KeyboardInterrupt). This is NOT a plugin validation pass or a diagnosed plugin failure. No runtime installation/repair was continued. An earlier public core clone under ignored .hermes-core was removed; no core code was patched or used to run tests. Coordinator reported the baseline's 88 unit/native/official checks passed independently and will run final native/plugin checks after applying the committed patch. Those coordinator statements are not represented as remote final-check evidence.

## Self-review: failure semantics and races

Malformed contract/tool input fails without a checkpoint. Missing pages, broken/repeated tokens, old/future observation times, unknown resources, unsupported event semantics and conflicting occurrence versions produce explicit partial gaps. Only complete resources count as checked; incomplete inventory blocks source success. Other fully observed sources can succeed independently. View output always says observed_busy_only and never promises global availability. Failed attempts preserve the previous successful interval, observation, resources and cursor. Source persistence uses the existing transaction; older observations cannot overwrite a newer completion for the same snapshot. Assembly introduces no shared cache/file/background state and therefore no new shared-write race.

Failure classifications validate the agent's normalized receipts, not proof of real connector access or exhaustive discovery. Incorrectly fabricated receipts cannot be detected by a provider-neutral stateless helper; the Skill requires actual original reads and honest scope. Full model/tool-trace acceptance remains necessary. Invalid/incomplete events do not silently establish empty coverage. Connector limitations on cancellation tombstones/expanded recurrence or overlap queries must remain partial until sufficient original evidence is available.

## Self-review: privacy and remaining limitations

All executed tests used temporary homes and synthetic events. No personal calendar/mail/connector data was inspected. No enabled permissions were expanded. The helper has no external API, write path, telemetry, provider dependency or event DB. Tool output retains only caller-supplied event data; the procedure instructs callers to include necessary original details and avoid unnecessary private payloads. Operational source checks save interval/coverage summaries, not event bodies. Existing private/direct-session boundaries remain enforced; group access is tested as rejected.

Cross-calendar copies may appear as multiple busy entries until verified original provenance resolves them; no fuzzy alias resolver was added. RRULE masters are not expanded locally; use the connector's authoritative expanded instances/exceptions. The model still owns actual discovery/reads, preparation relevance and user-facing rendering. Fixed-offset profiles cannot infer DST and state that limitation. Windows tzdata setup and new registered native-tool assertions were not executed on this remote host. Final native integration and official plugin validation, plus synthetic model-trace patrol acceptance, remain coordinator checks before release. No publication or deployment is authorized or performed.
