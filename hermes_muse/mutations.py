"""Tool-bound semantic CAS and replay journal; internal services keep their guards."""

import json
from .request_context import CURRENT_REQUEST
from .contracts import CAS, CREATES, validate
from .content_io import DomainError, revision, check_cancelled
from .views import Views, canonical
from .host import file_lock, profile_scope


def target(action, data):
    kind = CAS.get(action)
    if action == "feedback":
        kind = {"notification": "notice", "interest": "interest"}.get(data.get("kind"))
    if action == "forget":
        kind = {"notification": "notice", "operation_finding": "finding"}.get(
            data.get("kind"), data.get("kind")
        )
    if action == "finding_record" and not data.get("id"):
        from .store import digest

        return kind, digest("|".join(sorted(data.get("evidence", []))))
    if action == "source_check":
        # Canonical identity depends on stored aliases; resolve under the write lock.
        return kind, None
    return kind, "current" if action == "preferences" else data.get("id")


def object_state(views, kind, key):
    if (
        kind == "interest"
        and (views.record("interest", key) or {}).get("kind") == "idea"
    ):
        return views.object("idea", key)
    return views.object(kind, key)


def invoke(runtime, args, kwargs, callback):
    action, data = args.get("action"), args.get("data", {})
    validate(action, data)
    if (
        action not in CAS
        and action not in CREATES
        or action == "forget"
        and data.get("kind") == "content"
    ):
        return callback(args, **kwargs)
    from agent.delegation_context import is_delegated_child_context
    from .runtime import private_session, session_info

    if is_delegated_child_context() or not private_session(session_info()):
        raise DomainError(
            "permission_denied",
            "Business mutations require an authorized private parent context",
        )
    check_cancelled()
    views = Views(runtime.home)
    session = kwargs.get("session_id", "")
    with profile_scope(runtime.home):
        run = runtime.service.runs.bind(kwargs.get("task_id"))
    if not run:
        if not session:
            raise DomainError(
                "permission_denied", "A trusted originating session is required"
            )
        if data.get("signal_id"):
            with runtime.store.transaction() as db:
                signal = runtime.service.require_signal(db, data["signal_id"])
            if signal["session_id"] != session:
                raise DomainError(
                    "permission_denied", "Signal belongs to another session"
                )
        owner = data.get("goal_id") or (
            data.get("id")
            if action == "forget"
            and data.get("kind") == "goal"
            else None
        )
        if owner and runtime.store.goal(owner)[0].get("session_id") != session:
            raise DomainError("permission_denied", "Goal is outside this session")
        if action == "preferences" and not data.get("signal_id"):
            raise DomainError(
                "permission_denied", "Preference changes require a current user signal"
            )
    if action == "interest_record" and not data.get("id"):
        from .store import digest

        data = {**data, "id": digest(views.scope() + action + data["request_id"])[:12]}
        args = {**args, "data": data}
    kind, key = target(action, data)
    if action in CREATES:
        from .store import digest

        if action == "interest_record":
            kind, key = "interest", data["id"]
        elif action in {"feed_add", "notification_add"}:
            kind, key = (
                ("feed" if action == "feed_add" else "notice"),
                digest(data.get("event_key", "")),
            )
        elif action == "idea_add":
            kind, key = (
                "idea",
                digest(
                    (data.get("goal_id") or "context:") + data.get("title", "").strip()
                ),
            )
    if (
        not run
        and kind in {"notice", "feed", "interest", "idea"}
        and key
    ):
        try:
            _, record, _ = object_state(views, kind, key)
        except DomainError as exc:
            if exc.code != "not_found":
                raise
            record = {}
        origin = record.get("session_id")
        if record.get("goal_id"):
            origin = runtime.store.goal(record["goal_id"])[0].get("session_id")
        if origin and origin != session:
            raise DomainError(
                "permission_denied", "Object is outside this originating session"
            )
    journal = revision(canonical([views.scope(), action, data["request_id"]]))
    signature = revision(canonical(data))
    with file_lock(runtime.store.path("mutations.lock")):
        if action == "source_check":
            with runtime.store.transaction() as db:
                key, _, _ = runtime.service.source_identity(data, db)
        old = runtime.store.read("mutation_request", journal)
        if old:
            if old["signature"] != signature:
                raise DomainError(
                    "idempotency_conflict", "request_id arguments changed"
                )
            if old.get("result") is not None:
                raw = runtime._receipt(old["result"], action=action, data=data)
                bounded = json.loads(raw)
                if bounded != old["result"]:
                    runtime.store.write("mutation_request", journal, {**old, "result": bounded})
                return raw
            if kind and key:
                try:
                    _, observed, recovered_revision = object_state(views, kind, key)
                except DomainError:
                    observed = {}
                if observed.get("_request_id") == journal and action in CREATES | {
                    "feedback",
                    "notification_refresh",
                    "notification_resolve",
                    "source_check",
                    "finding_record",
                }:
                    result = {
                        "ok": True,
                        "result": observed,
                        "revision": recovered_revision,
                        "recovered": True,
                    }
                    raw = runtime._receipt(result, action=action, data=data)
                    runtime.store.write(
                        "mutation_request",
                        journal,
                        {**old, "state": "complete", "result": json.loads(raw)},
                    )
                    return raw
            raise DomainError(
                "outcome_unknown",
                "Semantic request interrupted; inspect original object/receipt before any retry",
            )
        if (
            action == "interest_record"
            and views.record("interest", key)
            and "expected_revision" not in data
        ):
            raise DomainError(
                "revision_required", "Renewing interest requires its current revision"
            )
        if action in CAS or action == "interest_record" and "expected_revision" in data:
            if not kind or not key:
                raise DomainError(
                    "invalid_argument", "Object identity is required for CAS"
                )
            try:
                actual = object_state(views, kind, key)[2]
            except DomainError as exc:
                if exc.code != "not_found":
                    raise
                actual = "absent"
            identity = {"source_id": key} if action == "source_check" else {}
            # The exact read for this object (e.g. kind=notice, not notification) and its current revision string.
            identity["read"] = {"action": "content_read", "data": {"kind": kind, "id": key}}
            if "expected_revision" not in data:
                raise DomainError(
                    "revision_required",
                    "expected_revision required: resend this same call with expected_revision set to current_revision "
                    "(\"absent\" means a new object); the same request_id may be reused because nothing was written.",
                    current_revision=actual, **identity,
                )
            if not isinstance(data["expected_revision"], str):
                raise DomainError(
                    "invalid_argument",
                    "expected_revision is the revision string from content_read or a context list row, not the integer "
                    "_revision; resend with expected_revision set to current_revision.",
                    current_revision=actual, **identity,
                )
            if data["expected_revision"] != actual:
                raise DomainError(
                    "revision_conflict",
                    "Object changed: reread it with the read call, merge, then resend with a new request_id and "
                    "expected_revision set to the reread revision.",
                    current_revision=actual, **identity,
                )
        intent = {
            "signature": signature,
            "state": "pending",
            "action": action,
            "object_kind": kind,
            "object_id": key,
        }
        runtime.store.write("mutation_request", journal, intent)
        token = CURRENT_REQUEST.set(journal)
        try:
            result = json.loads(callback(args, **kwargs))
        finally:
            CURRENT_REQUEST.reset(token)
        if result.get("ok") and kind and key:
            try:
                result["revision"] = object_state(views, kind, key)[2]
            except DomainError:
                pass
        raw = runtime._receipt(result, action=action, data=data)
        runtime.store.write(
            "mutation_request",
            journal,
            {**intent, "state": "complete", "result": json.loads(raw)},
        )
        return raw
