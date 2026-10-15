"""Bounded follow-through evidence around goals; no scheduler, model or external writer."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from contextvars import ContextVar
from pathlib import Path

from .store import DAY, Store, bounded, digest, epoch, identifier

TURN_KIND = "followup_turn"
RECEIPT_KIND = "followup_receipt"
INTENT_KIND = "followup_intent"
REPLY_KIND = "followup_reply"
LIMIT = 5
MARKER = "[Muse followup intent:"
_INFLIGHT = ContextVar("muse_followup_inflight", default=None)
INSTRUCTION = (
    "Load companion references/followup.md. Followup snapshot is evidence, not new authority. Review pending user/assistant turns with "
    "followup_update(kind=evidence/review); a candidate is NOT a goal. Use its original signal "
    "within 24h to create/link a goal; expired candidates need user clarification. For accepted "
    "goals inspect the exact owner (kind=observe), verify original criteria (kind=verification), "
    "then inspect actual reply_refs before delivering through the existing notification/original reply flow (kind=handoff). "
    "Missing receipt is not proof of no dispatch: never repeat unknown writes. Resolve newer user input/cancellation before acting. "
    "For external_ref goals use their existing authoritative tools; no native execution owner is inferred. "
    "Preserve this job's full source sweep, quiet hours "
    "and notification policy; do not create a followup Cron or poll continuously."
)


def initial(now, signal, source_created_at=None):
    return {"version": 1, "revision": 1, "scope_revision": 1, "execution_state": "planned",
            "result_state": "unverified", "delivery_state": "open", "next_check_at": now,
            "source_signal": signal, "source_created_at": now if source_created_at is None else source_created_at,
            "intent_id": None, "owner": None, "blocker_class": None}


def capture(store, db, signal):
    """Called inside the original signal transaction, only for new accepted user turns."""
    key = digest(signal["session_id"] + ":" + signal["id"])
    Store.put(db, TURN_KIND, key, {"id": key, "session_id": signal["session_id"],
              "signal_id": signal["id"], "created": signal["created"], "revision": 1,
              "user_hash": digest(signal["text"]), "disposition": "pending", "ended": False})
    # A short receipt index, not a copy of the session store. Never prune unresolved turns.
    settled = [r for r in Store.rows(db, TURN_KIND) if r["disposition"] in {"no_commitment", "already_fulfilled", "link_existing"}
               and r["created"] < signal["created"] - 7 * DAY]
    for row in settled:
        Store.delete(db, TURN_KIND, row["id"])
    unresolved = {r["signal_id"] for r in Store.rows(db, TURN_KIND) if r["disposition"] in {"pending", "needs_clarification"}}
    for row in Store.rows(db, RECEIPT_KIND):
        if not row.get("intent_id") and row.get("turn_id") not in unresolved and row["observed_at"] < signal["created"] - 7 * DAY:
            Store.delete(db, RECEIPT_KIND, row["id"])
    try:
        open_sessions = {g.get("session_id") for g in store.goals() if g.get("followup") and g["status"] != "cancelled"
                         and g["followup"]["delivery_state"] not in {"confirmed", "suppressed"}}
    except (OSError, ValueError):
        return  # Optional retention must never lose intake because a goal needs repair.
    for row in Store.rows(db, REPLY_KIND):
        if row["session_id"] not in open_sessions and row["observed_at"] < signal["created"] - 7 * DAY:
            Store.delete(db, REPLY_KIND, row["id"])


def _safe_root(home):
    home = Path(home).resolve()
    root = home / "muse"
    if root.is_symlink() or (root / "state.db").is_symlink():
        raise ValueError("Followup state must be profile-local, not a symlink")
    return root


def snapshot(home, *, now=None, session_id=None, offset=0, exclude_turn=None, rotate=True, callback_owner=None):
    """Read-only and constructor-free. Failure is partial, never an empty success."""
    now = time.time() if now is None else now
    result = {"version": 1, "observed_at": now, "complete": True, "due": [], "turns": [], "orphan_receipts": [], "reply_refs": [],
              "instruction": INSTRUCTION}
    db = None
    try:
        root = _safe_root(home)
        records = {}
        if (root / "state.db").exists():
            db = sqlite3.connect((root / "state.db").as_uri() + "?mode=ro", uri=True)
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            for kind in (TURN_KIND, RECEIPT_KIND, REPLY_KIND, "notification"):
                records[kind] = [json.loads(r[0]) for r in db.execute(
                    "SELECT data FROM records WHERE kind=? ORDER BY id", (kind,))]
        turns = [r for r in records.get(TURN_KIND, []) if r["disposition"] in {"pending", "needs_clarification"}
                 and (not session_id or r["session_id"] == session_id)
                 and r["signal_id"] != exclude_turn]
        turns.sort(key=lambda r: (r["created"], r["id"]))
        result["pending_total"] = len(turns)
        result["oldest_pending_at"] = turns[0]["created"] if turns else None
        # Rotation prevents an unresolved first page starving later obligations.
        if int(offset) < 0:
            raise ValueError("Offset must be nonnegative")
        turn_offset = int(offset) if offset or not rotate else (int(now // 1800) * LIMIT % len(turns) if turns else 0)
        selected = turns[turn_offset:turn_offset + LIMIT]
        result["turns"] = [{k: r.get(k) for k in (
            "id", "session_id", "signal_id", "created", "revision", "ended", "assistant_hash", "disposition")}
            | {"authority_expired": now - r["created"] > DAY} for r in selected]
        due = []
        goals_root = root / "workspace/goals"
        for path in sorted(goals_root.glob("*/GOAL.md")):
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Goal path escapes profile")
            first = path.read_text(encoding="utf-8").split("\n", 1)[0]
            if not first.startswith("<!-- hermes-muse ") or not first.endswith(" -->"):
                raise ValueError("Invalid managed goal metadata")
            goal = json.loads(first[len("<!-- hermes-muse "):-4])
            fu = goal.get("followup")
            if not fu or goal["status"] == "cancelled" or (session_id and goal.get("session_id") != session_id):
                continue
            if fu["delivery_state"] in {"confirmed", "suppressed"}:
                continue
            from .delivery import valid_basis, inferred_basis
            legacy = inferred_basis(Path(home), goal, records, now)
            if legacy:
                fu = {**fu, "delivery_basis": legacy}
            if fu["delivery_state"] in {"unknown", "queued"} and valid_basis(fu, records):
                continue
            owner_id = (fu.get("owner") or {}).get("id")
            if callback_owner and owner_id and owner_id != callback_owner:
                continue
            if fu.get("next_check_at", 0) > now and not (callback_owner and owner_id == callback_owner):
                continue
            if fu.get("blocker_class"):
                reason = fu["blocker_class"]
            elif fu["result_state"] == "verified":
                reason = "needs_handoff"
            elif fu.get("receipt_id") and fu["execution_state"] == "finished":
                reason = "needs_verification"
            elif fu.get("owner"):
                reason = "needs_verification" if fu["execution_state"] == "finished" else "needs_owner_readback"
            elif fu.get("intent_id"):
                reason = "outcome_unknown"
            elif goal.get("external_ref"):
                reason = "external_owner_requires_verification"
            else:
                reason = "missing_dispatch_receipt"
            due.append({"goal_id": goal["id"], "session_id": goal.get("session_id"), "external_ref_present": bool(goal.get("external_ref")),
                        "reason": reason, **{k: fu.get(k) for k in (
                            "revision", "scope_revision", "execution_state", "result_state",
                            "delivery_state", "owner", "intent_id", "receipt_id", "next_check_at",
                            "blocker_class", "notice_id", "delivery_ref")}})
        due.sort(key=lambda r: (bool(r["blocker_class"]), r["next_check_at"], r["goal_id"]))
        start = int(offset) if offset or not rotate else (int(now // 1800) * LIMIT % len(due) if due else 0)
        result["due_total"] = len(due)
        result["due"] = due[start:start + LIMIT]
        following = max(start, turn_offset) + LIMIT
        result["next_offset"] = following if following < max(len(due), len(turns)) else None
        result["partial_selection"] = len(due) > LIMIT or len(turns) > LIMIT
        orphans = [r for r in records.get(RECEIPT_KIND, []) if not r.get("intent_id")
                   and (not session_id or r.get("session_id") == session_id)]
        result["orphan_total"] = len(orphans)
        result["next_offset"] = following if following < max(len(due), len(turns), len(orphans)) else None
        from .content_io import revision
        from .views import canonical, Views
        result["snapshot_revision"] = revision(canonical([Views(home).scope(), due, turns, orphans]))
        result["orphan_receipts"] = orphans[int(offset):int(offset) + LIMIT]
        result["partial_selection"] |= len(orphans) > LIMIT
        sessions = {r["session_id"] for r in due}
        result["reply_refs"] = sorted([r for r in records.get(REPLY_KIND, []) if r["session_id"] in sessions],
                                      key=lambda r: r["observed_at"], reverse=True)[:LIMIT]
        return result
    except Exception as exc:
        return {**result, "complete": False, "error": type(exc).__name__,
                "instruction": INSTRUCTION + " Followup metadata is partial/unavailable; do not infer no work."}
    finally:
        if db is not None:
            db.rollback()
            db.close()


def context(home, **kwargs):
    """Small references only: core may persist the user-message sidecar."""
    data = snapshot(home, **kwargs)
    if data["complete"] and not data.get("pending_total") and not data.get("due_total") and not data.get("orphan_total"):
        return ""
    while len(json.dumps(data, ensure_ascii=False).encode()) > 6000 and any(data[k] for k in ("due", "turns", "orphan_receipts", "reply_refs")):
        key = max(("due", "turns", "orphan_receipts", "reply_refs"), key=lambda k: len(data[k]))
        data[key].pop()
        data["partial_selection"] = True
        data["next_offset"] = data.get("next_offset") or LIMIT
    return "[Hermes Muse followup snapshot]\n" + json.dumps(data, ensure_ascii=False)


def recover_native_owner(home, intent):
    """Optional pinned-schema read adapter, bounded to this exact dispatch session/intent.

    No native API exposes lookup by intent. Unsupported/pruned/ambiguous journals stay unknown.
    Never create a native DB, copy task_json to Muse, or scan all sessions.
    """
    path = Path(home) / "state.db"
    if not path.exists() or path.is_symlink():
        return {"status": "unavailable"}
    db = None
    try:
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        db.execute("PRAGMA query_only=ON")
        rows = db.execute("SELECT delegation_id,task_json FROM async_delegations "
                          "WHERE origin_session_id=? AND dispatched_at>=? ORDER BY dispatched_at DESC LIMIT 26",
                          (intent["session_id"], intent["created"] - 1)).fetchall()
        if len(rows) > 25:
            return {"status": "partial"}
        matches = [key for key, raw in rows if Followups._marker(json.loads(raw or "{}")) == intent["id"]]
        return {"status": "found", "owner_id": matches[0]} if len(matches) == 1 else {"status": "ambiguous" if matches else "missing"}
    except (sqlite3.Error, ValueError, TypeError):
        return {"status": "unavailable"}
    finally:
        if db is not None:
            db.close()


def protocol_outcomes(value):
    """Native tool envelope + durable wrapper + native batch children; never worker report JSON."""
    if not isinstance(value, dict):
        return []
    envelopes = [value]
    if "state" in value and value.get("delegation_id") and isinstance(value.get("result"), dict):
        envelopes.append(value["result"])  # get_durable_delegation's documented result envelope
    outcomes = list(envelopes)
    for envelope in envelopes:
        children = envelope.get("results")
        if isinstance(children, list):
            outcomes.extend(x for x in children[:100] if isinstance(x, dict))
            if len(children) > 100:
                outcomes.append({"status": "unknown"})
    return outcomes


def native_failed(value):
    return any(str(x.get("state", x.get("status", ""))).lower() in
               {"failed", "failure", "error", "cancelled", "unknown", "timeout", "interrupted", "stalled"}
               or x.get("ok") is False or x.get("error") for x in protocol_outcomes(value))


def native_pending(value):
    return any(str(x.get("state", x.get("status", ""))).lower() in
               {"running", "dispatched", "pending", "finalizing"} for x in protocol_outcomes(value))


class Followups:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def finish_turn(self, session_id, turn_id, *, response=None, history=(), **flags):
        key = digest(session_id + ":" + turn_id)
        with self.store.transaction() as db:
            row = Store.get(db, TURN_KIND, key)
            message_id = None
            for msg in reversed(history or ()):
                if msg.get("role") == "assistant" and msg.get("content") == response and isinstance(msg.get("_row_id"), int):
                    message_id = msg["_row_id"]
                    break
            if response and (any(g.get("followup") and g.get("session_id") == session_id and g["status"] != "cancelled" for g in self.store.goals()) or any(r.get("session_id") == session_id for r in Store.rows(db, "memory_feedback"))):
                Store.put(db, REPLY_KIND, key, {"id": key, "session_id": session_id, "turn_id": turn_id,
                    "assistant_hash": digest(response), "message_id": message_id, "observed_at": self.service.clock()})
            if not row:
                return  # An internal result is not an inbound user event.
            if response:
                response_hash = digest(response)
                if row.get("assistant_hash") != response_hash:
                    row.update(assistant_hash=response_hash, disposition="pending")
                    # Native row IDs only; never invent an ID from the array position.
                    if message_id is not None:
                        row["assistant_message_id"] = message_id
            row.update(ended=True, interrupted=bool(flags.get("interrupted")),
                       failed=bool(flags.get("failed")))
            row["revision"] += 1
            Store.put(db, TURN_KIND, key, row)

    def _goal(self, key):
        return self.store.goal(identifier(key), with_fingerprint=True)

    def _save(self, goal, body, fingerprint):
        goal["followup"]["revision"] += 1
        self.store.save_goal(goal, body, expected_hash=fingerprint)

    def _gate(self, db, goal, fu, *, session_id="", turn_id="", allow_terminal=False, allow_inflight=False):
        if goal["status"] == "cancelled" or (goal["status"] != "active" and not allow_terminal):
            raise ValueError("Goal scope is closed")
        latest = Store.get(db, "session", goal.get("session_id"), {})
        turn = Store.get(db, TURN_KIND, digest(str(goal.get("session_id")) + ":" + str(latest.get("turn_id"))), {})
        source = Store.get(db, "signal", fu["source_signal"], {})
        if (turn.get("disposition") in {"pending", "needs_clarification"} and turn.get("signal_id") != fu["source_signal"]
                and turn.get("created", 0) >= fu.get("source_created_at", source.get("created", goal["created"]))
                and not (latest.get("active") and session_id == goal.get("session_id")
                         and turn_id and turn_id == latest.get("turn_id"))):
            raise ValueError("Review newer user input before background followup")
        if fu["execution_state"] in {"paused", "needs_user", "cancelled"} and not allow_terminal:
            raise ValueError("Followup requires user action or is paused")
        if fu["execution_state"] == "outcome_unknown" and not allow_terminal and not allow_inflight:
            raise ValueError("Execution outcome is unknown; read back the existing attempt, never relaunch")

    def update(self, data, *, session_id="", turn_id=""):
        kind = data.get("kind")
        if kind == "due":
            value = snapshot(self.store.home, now=self.service.clock(), offset=int(data.get("offset", 0)), rotate=False)
            if data.get('offset', 0) and not data.get('snapshot_revision'):
                raise ValueError('Followup continuation requires snapshot_revision; enumerate IDs before changing them')
            if data.get('snapshot_revision') and data['snapshot_revision'] != value.get('snapshot_revision'):
                from .content_io import DomainError
                raise DomainError('revision_conflict', 'Followup selection changed; restart at offset=0, then process IDs with current object revisions')
            return value
        if kind == "evidence":
            if data.get("goal_id"):
                goal, _, fingerprint = self._goal(data["goal_id"])
                return {"goal_id": goal["id"], "status": goal["status"], "followup": goal.get("followup"),
                        "fingerprint": fingerprint, "content_ref": {"kind": "goal", "id": goal["id"]}}
            if data.get("receipt_id"):
                receipt = self.store.read(RECEIPT_KIND, data["receipt_id"])
                if not receipt:
                    raise ValueError("Unknown native receipt")
                db = None
                try:
                    path = self.store.home / "state.db"
                    if not path.exists() or path.is_symlink():
                        raise ValueError("Native tool evidence unavailable")
                    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
                    db.execute("PRAGMA query_only=ON")
                    rows = db.execute("SELECT id,content FROM messages WHERE session_id=? AND tool_call_id=? AND role='tool' LIMIT 2",
                                      (receipt["session_id"], receipt["tool_call_id"])).fetchall()
                    if len(rows) != 1:
                        raise ValueError("Native tool evidence missing or ambiguous")
                    text = rows[0][1] or ""
                    offset = max(0, int(data.get("offset", 0)))
                    return {"receipt": receipt, "message_id": rows[0][0], "text": text[offset:offset + 12000],
                            "next_offset": offset + 12000 if offset + 12000 < len(text) else None, "complete": True}
                except (sqlite3.Error, ValueError):
                    return {"receipt": receipt, "complete": False, "gap": "Exact native tool evidence unavailable; do not infer success"}
                finally:
                    if db is not None:
                        db.close()
            if data.get("reply_id"):
                row = self.store.read(REPLY_KIND, data["reply_id"])
                if not row:
                    raise ValueError("Unknown reply reference")
                history = self.service.host.conversation(row["session_id"], row["observed_at"] - 5)
                matches = [m for m in history.get("messages", []) if m.get("role") == "assistant"
                           and digest(m.get("text", "")) == row["assistant_hash"]
                           and (not row.get("message_id") or m.get("id") == row["message_id"])]
                return {"reply": row, "evidence": matches[0] if len(matches) == 1 else None, "complete": len(matches) == 1,
                        "note": "Settled assistant text is not proof of transport delivery or user reading."}
            row = self.store.read(TURN_KIND, data["candidate_id"])
            if not row:
                raise ValueError("Unknown followup candidate")
            signal = self.store.read("signal", row["signal_id"], {})
            history = self.service.host.conversation(row["session_id"], row["created"] - 5)
            matches = [m for m in history.get("messages", []) if m.get("role") == "assistant"
                       and digest(m.get("text", "")) == row.get("assistant_hash")
                       and (not row.get("assistant_message_id") or m.get("id") == row["assistant_message_id"])]
            return {"candidate": row, "user_evidence": signal.get("text"),
                    "assistant_evidence": matches[0] if len(matches) == 1 else None,
                    "complete": bool(signal) and len(matches) == 1,
                    "note": "Exact source evidence only; missing/ambiguous evidence is not authority."}
        if kind == "review":
            return self.review(data)
        if kind == "adopt":
            with self.store.transaction() as db:
                goal, body, fingerprint = self._goal(data["goal_id"])
                if goal.get("followup") or goal["status"] != "active" or data.get("expected_fingerprint") != fingerprint:
                    raise ValueError("Adopt only an unchanged active legacy goal; never reactivate history")
                signal = self.service.require_signal(db, data.get("signal_id"))
                current = Store.get(db, "session", session_id, {})
                quote = bounded(data.get("source_quote"), 2000)
                if (signal.get("truncated") or signal["session_id"] != session_id or signal["id"] != turn_id
                        or current.get("turn_id") != turn_id or not current.get("active")
                        or len(quote) < 8 or quote not in signal["text"]):
                    raise ValueError("Legacy adoption requires this current live user's explicit unchanged scope, not Cron or recall")
                goal["progress"] = (goal.get("progress", []) + [{"at": self.service.clock(), "text": "Current user accepted follow-through within unchanged criteria", "previous_source": goal.get("source_signal")}])[-50:]
                goal.update(source_signal=signal["id"], session_id=signal["session_id"], followup=initial(self.service.clock(), signal["id"], signal["created"]))
                self.store.save_goal(goal, body, expected_hash=fingerprint)
                return goal["followup"]
        if kind == "observe":
            return self.observe(data, session_id=session_id, turn_id=turn_id)
        if kind not in {"intent", "bind_receipt", "verification", "handoff", "block", "resume", "advance"}:
            raise ValueError("Unknown followup kind; load references/followup.md")
        with self.store.transaction() as db:
            goal, body, fingerprint = self._goal(data["goal_id"])
            fu = goal.get("followup")
            if not fu or data.get("expected_revision") != fu["revision"]:
                raise ValueError("Followup revision changed; reread current metadata")
            self._gate(db, goal, fu, session_id=session_id, turn_id=turn_id, allow_terminal=kind in {"handoff", "verification", "resume", "block"})
            if kind == "intent":
                return self._intent(db, goal, body, fingerprint, data, session_id=session_id)
            if kind == "bind_receipt":
                receipt = Store.get(db, RECEIPT_KIND, data.get("receipt_id"), {})
                if (fu.get("intent_id") or receipt.get("intent_id") or not receipt.get("tool_call_id")
                        or receipt.get("session_id") != goal.get("session_id")
                        or receipt.get("turn_id") != goal["source_signal"]):
                    raise ValueError("Only an exact orphan call from this goal's original user turn can be linked")
                key = digest("recovered:" + receipt["id"] + ":" + goal["id"])
                intent = {"id": key, "goal_id": goal["id"], "session_id": receipt["session_id"],
                          "source_session_id": goal["session_id"], "scope_revision": fu["scope_revision"],
                          "tool": "delegate_task", "state": "receipt", "created": receipt["observed_at"],
                          "receipt_id": receipt["id"]}
                receipt.update(intent_id=key, scope_revision=fu["scope_revision"])
                Store.put(db, INTENT_KIND, key, intent)
                Store.put(db, RECEIPT_KIND, receipt["id"], receipt)
                fu.update(intent_id=key, receipt_id=receipt["id"], owner=receipt["owner"],
                          execution_state="finished" if receipt["terminal"] else "waiting_external", blocker_class=None)
                if receipt["native_status"] == "unknown":
                    fu.update(execution_state="outcome_unknown", blocker_class="review_required")
            elif kind == "resume":
                signal = self.service.require_signal(db, data.get("signal_id"))
                latest = Store.get(db, "session", goal.get("session_id"), {})
                if goal["status"] != "active" or signal["session_id"] != goal["session_id"] or latest.get("turn_id") != signal["id"]:
                    raise ValueError("Resume needs the current real user input in this source session")
                fu["scope_revision"] += 1
                if fu.get("intent_id"):
                    intent = Store.get(db, INTENT_KIND, fu["intent_id"])
                    if intent:
                        intent["scope_revision"] = fu["scope_revision"]
                        Store.put(db, INTENT_KIND, intent["id"], intent)
                fu.update(execution_state="waiting_external" if fu.get("owner") else "outcome_unknown" if fu.get("intent_id") else "planned",
                          result_state="unverified", receipt_id=None, delivery_basis=None, delivery_state="open", notice_id=None, reply_id=None, delivery_ref=None,
                          blocker_class="review_required" if fu.get("intent_id") and not fu.get("owner") else None, recovery_attempted=False)
            elif kind == "advance":
                receipt = Store.get(db, RECEIPT_KIND, fu.get("receipt_id"), {})
                if not receipt.get("terminal") or receipt.get("native_status") == "unknown" or fu["execution_state"] == "outcome_unknown":
                    raise ValueError("Unknown or running work cannot be replaced by a new attempt")
                if fu["result_state"] == "verified":
                    raise ValueError("Deliver the verified result; a new scope needs user authority")
                refs = data.get("sources")
                if not isinstance(refs, list) or not refs or any(not isinstance(x, str) or not x.strip() for x in refs):
                    raise ValueError("Read back the previous outcome before advancing within accepted criteria")
                step = bounded(data.get("next_action"), 2000)
                goal["progress"] = (goal.get("progress", []) + [{"at": self.service.clock(), "text": step, "sources": refs, "previous_receipt": receipt["id"]}])[-50:]
                fu.update(scope_revision=fu["scope_revision"] + 1, execution_state="planned", result_state="unverified",
                          intent_id=None, receipt_id=None, owner=None, blocker_class=None, next_action=step, checks=0)
            elif kind == "block":
                state = data.get("execution_state")
                if state not in {"needs_user", "paused", "outcome_unknown"}:
                    raise ValueError("Block state must be needs_user/paused/outcome_unknown")
                if state == "paused":
                    self.service.require_signal(db, data.get("signal_id"))
                fu.update(execution_state=state, blocker_class="needs_user" if state == "needs_user" else "review_required",
                          blocker_reason=bounded(data.get("reason"), 2000))
            elif kind == "verification":
                from .evidence import resolve
                resolved = resolve(self.service, data.get("evidence_refs"), goal)
                result = data.get("result_state")
                if result not in {"verified", "failed"}:
                    raise ValueError("Verification must be verified/failed")
                refs = data.get("sources")
                verified = epoch(data.get("verified_at"))
                if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or not r.strip() or len(r) > 2000 for r in refs):
                    raise ValueError("Verification needs original result/artifact references")
                if not self.service.clock() - DAY <= verified <= self.service.clock():
                    raise ValueError("Verification needs current observed evidence")
                receipt = Store.get(db, RECEIPT_KIND, fu.get("receipt_id"), {})
                if receipt.get("native_status") == "unknown":
                    raise ValueError("Unknown execution is not verified success or verified failure")
                if fu.get("intent_id") and (not receipt or not receipt.get("terminal")):
                    raise ValueError("Owner is not terminal; record partial progress, not final verification")
                if result == "verified" and receipt.get("failed"):
                    raise ValueError("Native failure cannot be verified successful")
                fu.update(result_state=result, execution_state="finished", blocker_class=None,
                          verification={"sources": refs, "evidence_refs": resolved, "verified_at": verified,
                                        "summary": bounded(data.get("summary"), 2000)})
            elif kind == "handoff":
                if fu["result_state"] != "verified":
                    raise ValueError("Verify the accepted result before handoff")
                refs = [name for name in ("reply_id", "notice_id", "retry_failed_notice_id") if data.get(name)]
                if len(refs) != 1:
                    raise ValueError("Handoff requires exactly one reply, notice or proven-failure retry reference")
                if data.get("retry_failed_notice_id"):
                    failed = Store.get(db, "notification", data["retry_failed_notice_id"], {})
                    if (failed.get("goal_id") != goal["id"] or failed.get("followup_scope_revision") != fu["scope_revision"]
                            or failed.get("status") != "failed" or not failed.get("definitive_not_accepted")):
                        raise ValueError("Retry requires this scope's trusted proof that transport did not accept the original send")
                    if fu.get("retry_failed_notice_id") == failed["id"]:
                        return fu
                    fu.update(retry_failed_notice_id=failed["id"], delivery_state="open", notice_id=None,
                              delivery_basis=None, blocker_class=None)
                    self._save(goal, body, fingerprint)
                    return fu
                if data.get("reply_id"):
                    reply = Store.get(db, REPLY_KIND, data["reply_id"], {})
                    if reply.get("session_id") != goal["session_id"] or reply.get("observed_at", 0) < fu.get("source_created_at", goal["created"]):
                        raise ValueError("Reply must belong to this accepted source session and follow the original user request")
                    history = self.service.host.conversation(reply["session_id"], reply["observed_at"] - 5)
                    from .delivery import reply_evidence
                    readable, relevant = reply_evidence(goal, reply, history)
                    if readable and not relevant:
                        raise ValueError("Reply does not contain this verified result or artifact reference")
                    if relevant:
                        from .delivery import basis
                        new_basis = basis(fu, "reply", reply["id"], "recorded_unconfirmed", self.service.clock())
                        if all((fu.get("delivery_basis") or {}).get(k) == v for k,v in new_basis.items() if k != "noted_at"):
                            return fu
                        fu["delivery_basis"] = new_basis
                    fu.update(reply_id=reply["id"], delivery_state="unknown", blocker_class="delivery_unknown",
                              delivery_note=bounded(data.get("reason"), 2000))
                    checks = fu.get("delivery_checks", 0) + 1
                    fu["delivery_checks"] = checks
                    fu["next_check_at"] = self.service.clock() + (1800 if checks == 1 else 7200 if checks == 2 else 28800)
                    if not relevant and checks >= 3:
                        fu["blocker_class"] = "review_required"
                    self._save(goal, body, fingerprint)
                    return fu
                notice = Store.get(db, "notification", data.get("notice_id"), {})
                if (not notice or notice.get("goal_id") != goal["id"] or not notice.get("final_result")):
                    raise ValueError("Use this goal's actual final-result notification")
                if notice.get("followup_scope_revision") != fu["scope_revision"] or notice.get("followup_verified_at") != fu.get("verification", {}).get("verified_at"):
                    raise ValueError("Notice belongs to a different scope or verification version")
                from .delivery import basis
                new_basis = basis(fu, "notice", notice["id"], notice["status"], self.service.clock())
                if all((fu.get("delivery_basis") or {}).get(k) == v for k,v in new_basis.items() if k != "noted_at"):
                    return fu
                fu["delivery_basis"] = new_basis
                status = notice["status"]
                fu.update(notice_id=notice["id"], delivery_state=(
                    "confirmed" if status == "sent" else "unknown" if status in {"unknown", "failed", "cancelled"}
                    else "queued" if status in {"queued", "dispatching", "transport_queued"} else "prepared"),
                    blocker_class="delivery_" + status if status in {"unknown", "failed", "cancelled"} else None)
                if status == "sent":
                    fu["delivery_ref"] = {k: notice.get(k) for k in ("id", "job_id", "execution_id")}
            fu["next_check_at"] = self.service.clock()
            self._save(goal, body, fingerprint)
            return fu

    def review(self, data):
        if set(data) - {"kind", "candidate_id", "expected_revision", "disposition", "goal_ids", "reason"}:
            raise ValueError("Review uses the original signal; caller cannot replace it")
        with self.store.transaction() as db:
            row = Store.get(db, TURN_KIND, data["candidate_id"])
            if not row or data.get("expected_revision") != row["revision"]:
                raise ValueError("Candidate revision changed")
            disposition = data.get("disposition")
            if disposition not in {"no_commitment", "already_fulfilled", "link_existing", "needs_clarification"}:
                raise ValueError("Review needs a semantic disposition")
            if disposition == "link_existing":
                signal = self.service.require_signal(db, row["signal_id"])
                if signal.get("truncated"):
                    raise ValueError("Original source was truncated; clarify scope rather than promoting the candidate")
                if signal["session_id"] != row["session_id"] or digest(signal["text"]) != row["user_hash"]:
                    raise ValueError("Original user source changed")
                ids = data.get("goal_ids")
                if not isinstance(ids, list) or not ids:
                    raise ValueError("Create a goal with the ORIGINAL signal first, then link it")
                for key in ids:
                    goal, _ = self.store.goal(key)
                    if goal["status"] != "active" or goal["source_signal"] != row["signal_id"] or goal["session_id"] != row["session_id"]:
                        raise ValueError("Goal does not belong to this accepted source")
                row["goal_ids"] = ids
            row.update(disposition=disposition, reason=bounded(data.get("reason"), 2000),
                       revision=row["revision"] + 1)
            Store.put(db, TURN_KIND, row["id"], row)
            return row

    def _intent(self, db, goal, body, fingerprint, data, *, session_id=""):
        fu = goal["followup"]
        if data.get("tool", "delegate_task") != "delegate_task":
            raise ValueError("Only native delegation has a verified dispatch adapter; shell/Paseo remain external/unknown")
        if fu.get("intent_id"):
            previous = Store.get(db, INTENT_KIND, fu["intent_id"], {})
            if previous.get("state") == "prepared":
                return previous
            raise ValueError("Existing dispatch may have executed; observe/verify it, never blindly relaunch")
        key = digest(goal["id"] + ":" + str(fu["scope_revision"]) + ":" + str(fu["revision"]))
        row = {"id": key, "goal_id": goal["id"], "session_id": session_id or goal.get("session_id"),
               "source_session_id": goal.get("session_id"),
               "scope_revision": fu["scope_revision"], "tool": "delegate_task", "state": "prepared",
               "created": self.service.clock()}
        Store.put(db, INTENT_KIND, key, row)
        fu.update(intent_id=key, next_check_at=self.service.clock(), blocker_class=None)
        self._save(goal, body, fingerprint)
        return row

    def dispatch(self, goal_id, callback, request, *, session_id="", turn_id="", tool_call_id=None):
        """Own dispatch: durable intent precedes provider call, receipt follows it."""
        if not goal_id:
            return callback(request)
        with self.store.transaction() as db:
            goal, body, fingerprint = self._goal(goal_id)
            fu = goal.get("followup")
            if fu:
                self._gate(db, goal, fu, session_id=session_id, turn_id=turn_id)
                intent = self._intent(db, goal, body, fingerprint, {"tool": "delegate_task"}, session_id=session_id)
                if tool_call_id:
                    intent["origin_tool_call_id"] = tool_call_id
                    Store.put(db, INTENT_KIND, intent["id"], intent)
        if not fu:
            return callback(request)  # Preserve the legacy API, without auto-adopting its lifecycle.
        request = dict(request)
        tag = MARKER + intent["id"] + "]"
        if "tasks" in request:
            request["tasks"] = [{**t, "context": tag + "\n" + t.get("context", "")} for t in request["tasks"]]
            request["context"] = tag + "\n" + request.get("context", "")
        else:
            request["context"] = tag + "\n" + request.get("context", "")
        blocked = self.pre_tool("delegate_task", request, session_id=intent["session_id"], turn_id=turn_id)
        if blocked:
            raise ValueError(blocked["message"])
        token = _INFLIGHT.set(intent["id"])
        try:
            result = callback(request)
        except BaseException:
            # The provider might have accepted before raising. Preserve the uncertainty.
            self.unknown(intent["id"])
            raise
        finally:
            _INFLIGHT.reset(token)
        actual = self.store.read(INTENT_KIND, intent["id"], {})
        self.receipt("delegate_task", request, result, session_id=intent["session_id"],
                     tool_call_id=actual.get("tool_call_id") or intent.get("origin_tool_call_id") or intent["id"], turn_id=turn_id)
        if not isinstance(result, dict) or result.get("error") or result.get("ok") is False:
            self.unknown(intent["id"])
            error = ValueError("Native dispatch returned an error; inspect the exact outcome before retrying")
            error.native_result = result
            raise error
        return result

    @staticmethod
    def _marker(args):
        contexts = [args.get("context", "")] + [t.get("context", "") for t in args.get("tasks", []) if isinstance(t, dict)]
        found = set()
        for value in contexts:
            found.update(re.findall(r"\[Muse followup intent:([a-f0-9]{24})\]", str(value)))
        return next(iter(found)) if len(found) == 1 else None

    def pre_tool(self, tool_name, args, *, session_id="", **kwargs):
        if tool_name != "delegate_task":
            return
        key = self._marker(args)
        if not key:
            return
        with self.store.transaction() as db:
            intent = Store.get(db, INTENT_KIND, key)
            if not intent or intent["session_id"] != session_id:
                return {"action": "block", "message": "Followup intent is not owned by this session"}
            goal, body, fingerprint = self._goal(intent["goal_id"])
            fu = goal["followup"]
            if intent["scope_revision"] != fu["scope_revision"]:
                return {"action": "block", "message": "Followup scope changed"}
            try:
                self._gate(db, goal, fu, session_id=session_id, turn_id=kwargs.get("turn_id", ""),
                           allow_inflight=_INFLIGHT.get() == key)
            except ValueError as exc:
                return {"action": "block", "message": str(exc)}
            if intent["state"] != "prepared":
                if (intent["state"] == "attempt_requested" and not intent.get("tool_call_id")
                        and kwargs.get("tool_call_id") and _INFLIGHT.get() == key):
                    intent["tool_call_id"] = kwargs["tool_call_id"]
                    Store.put(db, INTENT_KIND, key, intent)
                    return
                return {"action": "block", "message": "Followup dispatch already attempted; inspect outcome"}
            intent.update(state="attempt_requested", tool_call_id=kwargs.get("tool_call_id"))
            Store.put(db, INTENT_KIND, key, intent)
            fu.update(execution_state="outcome_unknown", blocker_class="receipt_pending")
            self._save(goal, body, fingerprint)

    def unknown(self, key, *, recovery_attempted=False):
        with self.store.transaction() as db:
            intent = Store.get(db, INTENT_KIND, key)
            if not intent:
                return
            goal, body, fingerprint = self._goal(intent["goal_id"])
            fu = goal["followup"]
            if goal["status"] != "cancelled" and intent["scope_revision"] == fu["scope_revision"]:
                if fu["execution_state"] not in {"paused", "needs_user"}:
                    fu.update(execution_state="outcome_unknown", blocker_class="review_required")
                fu["recovery_attempted"] = fu.get("recovery_attempted", False) or recovery_attempted
                self._save(goal, body, fingerprint)

    def receipt(self, tool_name, args, result, *, session_id="", tool_call_id=None, **kwargs):
        if tool_name != "delegate_task":
            return
        if kwargs.get("status") == "blocked":
            return  # A rejected replay is not a new provider receipt for the original attempt.
        try:
            native = json.loads(result) if isinstance(result, str) else result
        except (ValueError, TypeError):
            return
        if not isinstance(native, dict):
            return
        owner_id = native.get("delegation_id")
        if owner_id is not None and (not isinstance(owner_id, str) or not owner_id.strip() or len(owner_id) > 160):
            return
        state = str(native.get("state", native.get("status", "completed" if isinstance(native.get("results"), list) else "unknown"))).lower()
        if state in {"success", "succeeded"}:
            state = "completed"
        if state in {"error", "failure", "timeout", "interrupted", "stalled"}:
            state = "failed"
        terminal = state in {"completed", "failed", "cancelled", "unknown"} and not native_pending(native)
        if not owner_id and not tool_call_id:
            return  # No verifiable identity.
        failed = native_failed(native)
        rid = digest("native:" + str(owner_id)) if owner_id else digest("tool:" + session_id + ":" + tool_call_id)
        key = self._marker(args)
        with self.store.transaction() as db:
            intent = Store.get(db, INTENT_KIND, key) if key else None
            if intent and intent["session_id"] != session_id:
                return
            if key and Store.get(db, "forgotten", "followup_intent:" + key):
                return
            prior = Store.get(db, RECEIPT_KIND, rid)
            if prior and prior.get("terminal") and not terminal:
                return
            if prior and prior.get("intent_id") and (not intent or prior["intent_id"] != intent["id"]):
                return  # Never merge distinct intents even if a tool reuses an owner ID.
            if intent and not owner_id:
                existing, _ = self.store.goal(intent["goal_id"])
                if existing.get("followup", {}).get("owner"):
                    return  # A lower-quality error cannot erase a previously proven owner.
            row = {"id": rid, "intent_id": intent["id"] if intent else None, "session_id": session_id,
                   "turn_id": kwargs.get("turn_id"),
                   "tool_call_id": tool_call_id, "owner": {"kind": "native_delegation", "id": owner_id} if owner_id else None,
                   "native_status": state, "terminal": terminal, "failed": failed,
                   "observed_at": self.service.clock(), "scope_revision": intent["scope_revision"] if intent else None}
            Store.put(db, RECEIPT_KIND, rid, row)
            if not intent or intent["session_id"] != session_id:
                return  # Orphan evidence grants no authority.
            goal, body, fingerprint = self._goal(intent["goal_id"])
            fu = goal["followup"]
            if goal["status"] == "cancelled" or intent["scope_revision"] != fu["scope_revision"]:
                return  # Late callback is evidence, never a reopening.
            intent.update(state="receipt", receipt_id=rid)
            Store.put(db, INTENT_KIND, key, intent)
            newly_bound = fu.get("receipt_id") != rid
            hold = (fu["execution_state"], fu.get("blocker_class")) if fu["execution_state"] in {"paused", "needs_user"} else None
            fu.update(owner=row["owner"], receipt_id=rid, blocker_class=None,
                      execution_state="finished" if terminal else "waiting_external",
                      next_check_at=self.service.clock() if terminal else self.service.clock() + 1800)
            if state == "unknown":
                fu.update(execution_state="outcome_unknown", blocker_class="review_required")
            if hold:
                fu.update(execution_state=hold[0], blocker_class=hold[1])
            if newly_bound or not prior or any(prior.get(k) != row[k] for k in ("native_status", "terminal", "failed")):
                self._save(goal, body, fingerprint)

    def observe(self, data, *, session_id="", turn_id=""):
        goal, _, _ = self._goal(data["goal_id"])
        fu = goal.get("followup", {})
        if data.get("expected_revision") != fu.get("revision"):
            raise ValueError("Followup revision changed")
        with self.store.transaction() as db:
            self._gate(db, goal, fu, session_id=session_id, turn_id=turn_id, allow_terminal=True)
            if fu["execution_state"] in {"paused", "needs_user"} and session_id != goal.get("session_id"):
                raise ValueError("Wait for the user's real action; Cron must not poll this hold")
            if fu.get("blocker_class") == "review_required" and (fu.get("recovery_attempted") or not fu.get("intent_id")) and session_id != goal.get("session_id"):
                raise ValueError("Owner recovery paused; wait for user/owner evidence instead of polling")
        owner = fu.get("owner") or {}
        if not owner and fu.get("receipt_id"):
            receipt = self.store.read(RECEIPT_KIND, fu["receipt_id"], {})
            if receipt.get("terminal") and receipt.get("native_status") != "unknown":
                return {"receipt": receipt, "instruction": "Joined native call is terminal, not business-verified. Read its exact tool evidence, verify criteria; do not redispatch."}
        if goal.get("external_ref") and not fu.get("intent_id"):
            return {"status": "owner_level", "instruction": "Inspect the exact external_ref with its existing authorized tools and actual result criteria. No native/per-prompt owner is inferred; never re-dispatch unknown work."}
        if owner.get("kind") != "native_delegation" or not owner.get("id"):
            intent = self.store.read(INTENT_KIND, fu.get("intent_id"), {})
            recovered = recover_native_owner(self.store.home, intent) if intent else {"status": "missing"}
            if recovered["status"] == "found":
                owner = {"kind": "native_delegation", "id": recovered["owner_id"]}
            else:
                if fu.get("intent_id"):
                    self.unknown(fu["intent_id"], recovery_attempted=True)
                return {"status": "unknown", "recovery": recovered["status"],
                        "instruction": "No exact native handle; do not relaunch or infer an owner from shell text."}
        from tools.async_delegation import get_durable_delegation
        native = get_durable_delegation(owner["id"])
        if not native:
            self.unknown(fu["intent_id"], recovery_attempted=True)
            return {"status": "unknown", "instruction": "Native receipt unavailable/expired; no retry of unknown work."}
        intent = self.store.read(INTENT_KIND, fu["intent_id"], {})
        self.receipt("delegate_task", {"context": MARKER + fu["intent_id"] + "]"}, native,
                     session_id=intent.get("session_id"), tool_call_id=fu["intent_id"])
        with self.store.transaction() as db:
            latest, body, fingerprint = self._goal(goal["id"])
            current = latest["followup"]
            self._gate(db, latest, current, session_id=session_id, turn_id=turn_id, allow_terminal=True)
            if current["execution_state"] == "waiting_external":
                count = current.get("checks", 0) + 1
                intent = Store.get(db, INTENT_KIND, current["intent_id"], {})
                current.update(checks=count, next_check_at=self.service.clock() + (1800, 7200, 28800)[min(count - 1, 2)])
                if self.service.clock() - intent.get("created", 0) >= DAY:
                    current.update(blocker_class="review_required", recovery_attempted=True)
                self._save(latest, body, fingerprint)
        return {"native": native, "followup": latest["followup"],
                "instruction": "Owner status is not business verification. Inspect original results/criteria, then verify and hand off."}
