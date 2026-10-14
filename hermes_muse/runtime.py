"""Plugin registration, conversation hooks and the single state tool."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path

from .handoff import MARKER, receiving_instructions, render_result
from .audit import Audit
from .host import HermesHost, ROOT, profile_scope
from .service import Companion
from .store import GOVERNANCE_JOBS, Store, is_background_message
from .followup import context as followup_context

log = logging.getLogger(__name__)
ACTIONS = ("content_read", "content_write", "memory_feedback_review", "installation_prepare", "context", "status", "conversation_read", "followup_update", "goal_create", "goal_update", "interest_record", "idea_add", "feedback",
           "preferences", "notification_add", "notification_refresh", "notification_queue", "notification_handoff", "notification_prepare", "feed_add", "feed_list",
           "feed_update", "calendar_window", "calendar_view", "source_check", "notification_resolve", "notification_review", "review_complete", "run_complete", "watch_create", "watch_stop", "delegate", "research_start", "research_status", "operations_read", "operations_complete", "operations_batch", "operations_evidence", "operations_commit", "finding_record", "forget")
SCHEMA = {"name": "muse_manage", "description": "Assemble calendar views, manage companion goals, temporary interests, reminders, Feed and background research and inspect native operations/findings. First read hermes-muse:companion for action-specific data fields. context returns live state and real user signal IDs. Never invent a signal ID, delivery receipt or authorization.",
          "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": list(ACTIONS)}, "data": {"type": "object", "description": "Action arguments documented by the companion Skill; omit for context/status."}}, "required": ["action"], "additionalProperties": False}}


def session_info():
    from gateway.session_context import get_session_env
    fields = {key: get_session_env("HERMES_SESSION_" + key.upper(), "") for key in
              ("id", "key", "platform", "chat_id", "chat_type", "thread_id", "user_id", "message_id", "scope_id", "parent_chat_id")}
    fields["cron"] = get_session_env("HERMES_CRON_SESSION", "") == "1"
    return fields


def private_session(info):
    return str(info.get("chat_type", "")).lower() not in {"group", "supergroup", "channel", "guild", "room"}


def route_from(info):
    if not private_session(info) or not info.get("platform") or not info.get("chat_id"):
        return None
    return {key: info[key] for key in ("platform", "chat_id", "chat_type", "thread_id", "user_id", "message_id", "scope_id", "parent_chat_id") if info.get(key)} | {"session_key": info.get("key", "")}


class Runtime:
    def __init__(self, ctx, home, *, quiet_seconds=300, plugin_root=ROOT):
        self.ctx, self.home, self.quiet_seconds = ctx, Path(home).resolve(), quiet_seconds
        self.store = Store(self.home)
        self.host = HermesHost(self.store, plugin_root=plugin_root)
        self.service = Companion(self.store, self.host)
        from .memory_feedback import MemoryFeedback
        self.memory_feedback = MemoryFeedback(self.store, self.service.clock)
        self.timers = {}
        self.delivery_turns = {}
        self.run_turns = {}
        self.followup_contexts = {}
        self.lock = threading.RLock()
        self.closed = False

    def handle(self, args, **kwargs):
        try:
            from .mutations import invoke
            return invoke(self, args, kwargs, self._handle)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc), "code": getattr(exc, "code", "invalid_argument"),
                               "retryable": False, **getattr(exc, "details", {})}, ensure_ascii=False)

    def _handle(self, args, **kwargs):
        try:
            if self.closed:
                raise ValueError("Plugin unloaded")
            # This core forwards session/task only to registry handlers. Its
            # execution wrapper binds trusted correlation ContextVars instead.
            # Version-specific read-only adapter; absence leaves IDs unknown.
            try:
                from tools import approval_context
                if approval_context._approval_session_id.get() == kwargs.get("session_id"):
                    kwargs = {**kwargs, "turn_id": approval_context._approval_turn_id.get(),
                              "tool_call_id": approval_context._approval_tool_call_id.get()}
            except (ImportError, AttributeError):
                pass
            info = session_info()
            if not private_session(info):
                raise ValueError("Personal Muse data is available in private/direct conversations only")
            from .content_io import DomainError
            from .views import Views
            if not isinstance(args, dict) or set(args) - {"action", "data"}:
                raise DomainError("invalid_argument", "Use action and data only")
            if len(json.dumps(args, ensure_ascii=False, allow_nan=False).encode()) > 512 * 1024:
                raise DomainError("size_limit", "Request exceeds 512 KiB")
            data = args.get("data", {})
            if not isinstance(data, dict):
                raise ValueError("data must be an object")
            action = args["action"]
            from .contracts import validate
            validate(action, data)
            from .contracts import CAS, CREATES
            if (action in CAS or action in CREATES) and not (action == "forget" and data.get("kind") == "content"):
                data = {k:v for k,v in data.items() if k not in {"expected_revision", "request_id", "scope_token"}}
            if action not in ACTIONS:
                raise ValueError("Unknown Muse action")
            from agent.delegation_context import is_delegated_child_context
            delegated = is_delegated_child_context()
            # Installed host exposes child identity, but no public object-grant propagation.
            # Do not trust allowed_ids supplied by a child; parent provides cropped evidence.
            if delegated and action not in {"calendar_window", "calendar_view"}:
                raise DomainError("permission_denied", "No trusted object grant in this child context; ask the parent for scoped evidence")
            if action in {"content_read", "feed_list", "calendar_window", "calendar_view"}:
                if action == "content_read":
                    view = Views(self.home)
                    parts = str(kwargs.get("task_id") or "").split(":", 2)
                    if len(parts) == 3 and parts[0] == "cron":
                        stored = view.record("run", parts[2]) or {}
                        owned = view.manifest()["jobs"].get(parts[1], {})
                        view.allow_hidden = bool(stored.get("status") == "running" and stored.get("job_id") == parts[1]
                                                 and (owned.get("key") == "nightly-review" or owned.get("owner") == data.get("id")))
                    result = view.read(data)
                elif action == "feed_list":
                    result = Views(self.home).read({**data, "kind": "feed"})
                else:
                    result = getattr(self.service, action)(data)
                return self._response(result)
            with profile_scope(self.home):
                self.service.operations.track(kwargs.get("session_id"), kwargs.get("task_id"))
                run = self.service.runs.bind(kwargs.get("task_id"))
                if run and kwargs.get("session_id"):
                    with self.lock:
                        self.run_turns[kwargs["session_id"]] = run
                delivery = self.host.current_delivery(kwargs.get("task_id"))
                if delivery and kwargs.get("session_id"):
                    with self.lock:
                        self.delivery_turns[kwargs["session_id"]] = delivery
                if action == "forget" and data.get("kind") == "content":
                    from .content import Content
                    result = Content(self.service).forget(data, session_id=kwargs.get("session_id", ""))
                elif action == "content_write":
                    from .content import Content
                    result = Content(self.service).write(data, session_id=kwargs.get("session_id", ""), run=run)
                elif action == "memory_feedback_review":
                    result = self.memory_feedback.review(data, kwargs.get("session_id", ""), kwargs.get("turn_id", ""))
                elif action == "installation_prepare":
                    from .installation import prepare
                    result = prepare(self, data, kwargs.get("session_id", ""), kwargs.get("turn_id", ""))
                elif action == "goal_update" and data.get("status") == "completed":
                    if not data.get("evidence_refs"):
                        raise ValueError("Completion requires structured evidence_refs for the accepted result or explicit user confirmation")
                    result = self.service.goal_update(data)
                elif action == "followup_update":
                    result = self.service.followups.update(data, session_id=kwargs.get("session_id", ""), turn_id=kwargs.get("turn_id", ""))
                elif action in {"context", "status"}:
                    self.host.reconcile()
                    parts = str(kwargs.get("task_id") or "").split(":", 2)
                    view = None
                    if len(parts) == 3 and parts[0] == "cron":
                        view = self.host.manifest()["jobs"].get(parts[1], {}).get("key")
                    result = self.service.context(view=view)
                    result["memory_feedback"] = self.memory_feedback.candidates(kwargs.get("session_id", ""))
                    result["scope_token"] = Views(self.home).scope()
                    result["read_semantics"] = "refreshes and reconciles; use content_read for a pure read"
                    if action == "status":
                        result["installation"] = self.host.manifest()
                        result["reviews"] = {job: self.store.read("meta", "last_review:" + job)
                                             for job in GOVERNANCE_JOBS}
                elif action in {"operations_batch", "operations_commit"}:
                    audit = Audit(self.service.operations)
                    from agent.subagent_lifecycle import get_active_subagent_parent
                    parent = get_active_subagent_parent()
                    remaining = getattr(getattr(parent, "iteration_budget", None), "remaining", None)
                    if action == "operations_batch" and isinstance(remaining, int) and remaining < 8:
                        result = {"available": True, "deferred": True, "assignments": [],
                                  "instruction": "The host has fewer than eight tool iterations left. Save findings and run_complete(partial) with the audit continuation, then finish normally. Do not launch another worker wave; the next hourly run resumes saved work."}
                    else:
                        result = audit.batch() if action == "operations_batch" else audit.commit(data)
                    self.service.runs.stage(run, "operations", {
                        "complete": bool(result.get("batch_complete")) and not result.get("more", True),
                        "phase": "allocated" if action == "operations_batch" else "reviewed",
                        **{k: result[k] for k in ("checkpoint", "allocated_slots", "reviewed_slots", "newly_reviewed_slots", "continuous_slots", "remaining_slots", "observed_at", "deferred") if k in result}})
                elif action == "operations_evidence":
                    result = self.service.operations.evidence(data)
                elif action in {"operations_read", "operations_complete", "finding_record"}:
                    method = {"operations_read": "read", "operations_complete": "complete", "finding_record": "finding"}[action]
                    result = getattr(self.service.operations, method)(data)
                    if action == "operations_read":
                        self.service.runs.stage(run, "operations", {"complete": False, "phase": "allocated", "allocated_events": len(result.get("events", [])), "allocated_executions": len(result.get("executions", [])), "receipt": result.get("token")})
                    if action == "operations_complete":
                        self.service.runs.stage(run, "operations", {"complete": not result["more"], "checkpoint": result["checkpoint"]})
                elif action == "run_complete":
                    result = self.service.runs.finish(run, data)
                elif action == "review_complete":
                    if run and data.get("job") != run["job"]:
                        raise ValueError("Review checkpoint must belong to this Cron job")
                    if run and run["job"].startswith("watch-"):
                        owned = self.host.manifest()["jobs"].get(run["job_id"], {})
                        goal, _ = self.store.goal(owned["owner"])
                        refs = data.get("source_check_ids")
                        if (data.get("goal_id") != goal["id"] or not isinstance(refs, list) or not refs
                                or data.get("stop_condition") != owned.get("stop_condition")):
                            raise ValueError("Watch review needs its actual goal, stop_condition and source_check_ids")
                        rows = [self.store.read("source_check", ref, {}) for ref in refs]
                        complete = all(r.get("status") == "checked" and r.get("started_at", r.get("started", 0)) >= run["started"] for r in rows)
                        result = {"complete": complete, "through": self.service.clock(), "goal_id": goal["id"],
                                  "goal_status": goal["status"], "stop_condition": data["stop_condition"], "source_check_ids": refs}
                    else:
                        result = self.service.review_complete(data)
                    self.service.runs.stage(run, "review", {"complete": result["complete"], "through": result["through"], "summary": data["summary"]})
                elif action == "preferences":
                    result = self.service.preference_update({k:v for k,v in data.items() if k != "signal_id"}, cron=info["cron"] or str(kwargs.get("task_id", "")).startswith("cron:"))
                elif action == "watch_create":
                    # Native cron identity, never a model-supplied ownership flag.
                    if info["cron"] or str(kwargs.get("task_id") or "").startswith("cron:"):
                        from hermes_cli.config import load_config_readonly
                        if load_config_readonly().get("cron", {}).get("allow_agent_scheduling") is not True:
                            raise ValueError("Cron watch creation is disabled by cron.allow_agent_scheduling; no job created. Existing goal follow-through continues.")
                    result = self.host.watch(data)
                elif action == "watch_stop":
                    result = self.host.stop_watch(data["job_id"])
                elif action == "delegate":
                    from .delegation import dispatch, validate
                    request = {k: v for k, v in data.items() if k != "goal_id"}
                    validate(request, owned_cron=bool(run or delivery))
                    result = self.service.followups.dispatch(data.get("goal_id"),
                        lambda req: Audit(self.service.operations).dispatch(req, lambda: dispatch(self.ctx, req, owned_cron=bool(run or delivery)), session_id=kwargs.get("session_id", ""), tool_call_id=kwargs.get("tool_call_id")), request,
                        session_id=kwargs.get("session_id", ""), turn_id=kwargs.get("turn_id", ""), tool_call_id=kwargs.get("tool_call_id"))
                elif action in {"research_start", "research_status"}:
                    from .research import start, poll
                    result = (start(self.store, self.ctx, data, owned_cron=bool(run or delivery), followups=self.service.followups,
                                    session_id=kwargs.get("session_id", ""), turn_id=kwargs.get("turn_id", ""), tool_call_id=kwargs.get("tool_call_id"))
                              if action == "research_start" else poll(self.store, self.ctx, data))
                elif action in {"notification_prepare", "notification_queue", "notification_handoff"}:
                    result = self.service.notification_queue(data, delivery if delivery and delivery.get("kind") != "report" else None)
                else:
                    if action == "notification_add" and not data.get("session_id"):
                        data = dict(data)
                        if data.get("goal_id"):
                            data["session_id"] = self.store.goal(data["goal_id"])[0].get("session_id")
                        elif data.get("interest_id"):
                            data["session_id"] = self.store.read("interest", data["interest_id"], {}).get("session_id")
                        elif not info["cron"]:
                            data["session_id"] = info["id"]
                    result = getattr(self.service, action)(data)
            return self._response(result)
        except Exception as exc:
            log.warning("Hermes Muse action %s failed: %s", args.get("action"), exc)
            error = {"ok": False, "error": str(exc), "code": getattr(exc, "code", "invalid_argument"), "retryable": getattr(exc, "code", "") in {"revision_conflict", "cursor_expired", "source_unavailable"}, **getattr(exc, "details", {})}
            if hasattr(exc, "native_result"):
                error["native"] = exc.native_result
            return json.dumps(error, ensure_ascii=False)

    @staticmethod
    def _response(result):
        from .content_io import DomainError
        raw = json.dumps({"ok": True, "result": result}, ensure_ascii=False, allow_nan=False)
        if len(raw.encode()) > 256 * 1024:
            raise DomainError("size_limit", "Response exceeds 256 KiB; request a smaller page or source/window batch")
        return raw

    def transform_output(self, response_text="", session_id="", **kwargs):
        with self.lock:
            delivery = self.delivery_turns.pop(session_id, None)
            run = self.run_turns.pop(session_id, None)
        if self.closed:
            return None
        with profile_scope(self.home):
            result = None
            if delivery:
                result = (render_result(response_text, delivery["route"]["deliver"])
                          if delivery.get("kind") == "report" else self.service.finalize_delivery(delivery))
            if run:
                self.service.runs.finalize(run, notifications=bool(delivery))
            return result

    def handoff(self, key):
        return self.service.notification_queue({"id": key})

    def pre_turn(self, session_id="", turn_id="", user_message="", platform="", parent_session_id="", **kwargs):
        info = session_info()
        if not self.closed and not parent_session_id and private_session(info) and str(kwargs.get("task_id", "")).startswith("cron:"):
            with profile_scope(self.home):
                run = self.service.runs.bind(kwargs.get("task_id"))
                if run:
                    with self.lock:
                        self.run_turns[session_id] = run
                    self.service.operations.track(session_id, kwargs.get("task_id"))
        if self.closed or parent_session_id or info["cron"] or platform in {"cron", "delegate", "subagent", "webhook", "msgraph_webhook", "kanban"} or not private_session(info):
            return None
        text = user_message if isinstance(user_message, str) else json.dumps(user_message, ensure_ascii=False)
        if text.lstrip().startswith(('[Cronjob "', "[Hermes Muse notification ", MARKER)):
            return {"context": receiving_instructions()}
        if is_background_message(text):
            match = re.match(r"^\[ASYNC DELEGATION (?:BATCH COMPLETE|COMPLETE|TASK FAILED) — ([A-Za-z0-9_-]+)(?:, task [0-9]+/[0-9]+)?\]", text.lstrip())
            value = self._followup_context(session_id, turn_id, callback_owner=match[1] if match else None)
            return {"context": value + "\nBackground process completion is intermediate evidence. Report only blockers, changed direction or verified results; do not infer goal completion."} if value else None
        if not session_id or not turn_id or not text.strip():
            return None
        with self.lock:
            timer = self.timers.pop(session_id, None)
            if timer:
                timer.cancel()
        self.service.signal(turn_id, session_id, text, route_from(info))
        return {"context": f"[Hermes Muse state pointer] This real user turn has signal_id={turn_id}. For goals, interests, feedback, reminders or Feed, load hermes-muse:companion and use muse_manage. When accepting or changing work, read its communication procedure: think through the outcome and practical consequences, persist the plan, verify actions and explain the useful judgment in the user's own conversational style. Read current state before using old memories as an active goal. This pointer does not authorize extra tasks.\n" + self._followup_context(session_id, turn_id, exclude_turn=turn_id) + self.memory_feedback.context(session_id)}

    def _followup_context(self, session_id, turn_id, **kwargs):
        with self.lock:
            cached = self.followup_contexts.get(session_id)
            if cached and cached[0] == turn_id:
                return cached[1]
            value = followup_context(self.home, now=self.service.clock(), session_id=session_id, **kwargs)
            self.followup_contexts[session_id] = (turn_id, value)
            return value

    def pre_tool(self, tool_name="", args=None, **kwargs):
        from agent.delegation_context import is_delegated_child_context
        if self.closed or is_delegated_child_context() or not private_session(session_info()):
            return None
        with profile_scope(self.home):
            return self.service.followups.pre_tool(tool_name, args or {}, **kwargs)

    def post_tool(self, tool_name="", args=None, result=None, **kwargs):
        from agent.delegation_context import is_delegated_child_context
        if self.closed or is_delegated_child_context() or not private_session(session_info()):
            return None
        with profile_scope(self.home):
            self.service.followups.receipt(tool_name, args or {}, result, **kwargs)
            self.memory_feedback.capture(tool_name, args or {}, result, **kwargs)

    def post_turn(self, session_id="", turn_id="", **kwargs):
        if self.closed:
            return
        self.service.followups.finish_turn(session_id, turn_id, response=kwargs.get("assistant_response"), history=kwargs.get("conversation_history", ()))
        self.memory_feedback.finish(session_id, turn_id, kwargs.get("assistant_response") or "")
        if private_session(session_info()):
            self.service.operations.track(session_id, kwargs.get("task_id"))
        session = self.store.read("session", session_id)
        if not session or session.get("turn_id") != turn_id:
            return
        with self.store.transaction() as db:
            session = self.store.get(db, "session", session_id, {})
            if session.get("turn_id") != turn_id:
                return
            session["active"] = False
            self.store.put(db, "session", session_id, session)
        signal = self.store.read("signal", turn_id, {})
        if len(signal.get("text", "")) < 80:
            return
        with self.lock:
            if self.closed:
                return
            previous = self.timers.pop(session_id, None)
            if previous:
                previous.cancel()
            timer = threading.Timer(self.quiet_seconds, self.quiet_pass, args=(session_id, turn_id))
            timer.daemon = True
            self.timers[session_id] = timer
            timer.start()

    def quiet_pass(self, session_id, turn_id):
        with self.lock, profile_scope(self.home):
            if self.closed:
                return
            session = self.store.read("session", session_id, {})
            if session.get("active") or session.get("turn_id") != turn_id:
                return
            today = self.host.local_now(time.time()).date().isoformat()
            with self.store.transaction() as db:
                count = self.store.get(db, "budget", "quiet:" + today, 0)
                if count >= 3:
                    return
                self.store.put(db, "budget", "quiet:" + today, count + 1)
            self.host.wake("memory-upkeep")
            self.timers.pop(session_id, None)

    def end_turn(self, session_id="", turn_id="", **kwargs):
        if self.closed:
            return
        self.service.followups.finish_turn(session_id, turn_id, **kwargs)
        with self.lock:
            self.delivery_turns.pop(session_id, None)
            self.run_turns.pop(session_id, None)
        # Failed/interrupted turns must also release the local attention hold.
        with self.store.transaction() as db:
            row = self.store.get(db, "session", session_id)
            if row and row.get("turn_id") == turn_id:
                row["active"] = False
                self.store.put(db, "session", session_id, row)

    def close(self):
        with self.lock:
            self.closed = True
            for timer in self.timers.values():
                timer.cancel()
            self.timers.clear()
            self.delivery_turns.clear()
            self.run_turns.clear()
            self.followup_contexts.clear()


def register(ctx, *, plugin_root=ROOT):
    from hermes_constants import get_hermes_home
    required = ("register_tool", "register_skill", "register_system_prompt_section", "register_hook", "on_unload")
    if any(not callable(getattr(ctx, name, None)) for name in required):
        raise RuntimeError("Hermes Muse needs Hermes 0.21.5+ with prompt sections, plugin skills and unload hooks")
    runtime = Runtime(ctx, get_hermes_home(), plugin_root=plugin_root)
    runtime.host.initialize()
    prompt = (runtime.host.root / "prompts/system.md").read_text(encoding="utf-8").replace("{{MUSE_HOME}}", str(runtime.store.root)).replace("{{HERMES_HOME}}", str(runtime.home))
    ctx.register_skill("companion", runtime.host.root / "skills/companion/SKILL.md", description="Calendar views, goals, memory upkeep, proactive reminders, reflection, Feed and research lifecycle")
    ctx.register_system_prompt_section("hermes-muse.companion", prompt, position="after_memory", max_chars=4000)
    ctx.register_tool(name="muse_manage", toolset="muse", schema=SCHEMA, handler=runtime.handle)
    ctx.register_hook("pre_tool_call", runtime.pre_tool)
    ctx.register_hook("post_tool_call", runtime.post_tool)
    ctx.register_hook("on_skill_lifecycle", runtime.memory_feedback.lifecycle)
    ctx.register_hook("pre_llm_call", runtime.pre_turn)
    ctx.register_hook("post_llm_call", runtime.post_turn)
    ctx.register_hook("transform_llm_output", runtime.transform_output)
    ctx.register_hook("on_session_end", runtime.end_turn)
    ctx.on_unload(runtime.close)
