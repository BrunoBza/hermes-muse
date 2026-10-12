"""Read native operation evidence; keep only checkpoints, references and findings."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager

from .store import DAY, bounded, digest, epoch

GROUPS = {"group", "supergroup", "channel", "guild", "room"}
INSPECTION = {"context", "status", "conversation_read", "operations_read", "operations_complete", "operations_batch", "operations_evidence", "operations_commit", "finding_record"}


@contextmanager
def reader(path):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def calls(row):
    value = row.get("tool_calls") or []
    return json.loads(value) if isinstance(value, str) else value


def inspection(call):
    fn = call.get("function", {})
    try:
        args = fn.get("arguments", {})
        args = json.loads(args) if isinstance(args, str) else args
        if fn.get("name") == "tool_call":
            nested = args.get("calls")
            return bool(nested) and isinstance(nested, list) and all(
                inspection({"function": item}) for item in nested)
        return (fn.get("name") == "muse_manage" and args.get("action") in INSPECTION
                or fn.get("name") in {"skill_view", "tool_search", "tool_describe"})
    except (AttributeError, TypeError, ValueError):
        return False


def failed_result(content):
    """Keep failures even when the operation was only an inspection."""
    try:
        value = json.loads(content or "null")
    except (ValueError, TypeError):
        return any(word in str(content).lower() for word in ("error", "failed", "denied"))
    if isinstance(value, dict):
        return (value.get("ok") is False or value.get("success") is False
                or value.get("isError") is True or bool(value.get("error"))
                or value.get("status") in {"error", "failed"})
    return False


def preview(event):
    """An index, never a replacement for source evidence. Full bodies stay in native history."""
    text = json.dumps(event, ensure_ascii=False)
    linked = event.get("related_call", {}).get("call")
    action = linked or event.get("tool_calls") or []
    return {"ref": event["ref"], "session_id": event.get("session_id"), "role": event.get("role"),
            "tool_name": event.get("tool_name"), "call_preview": json.dumps(action, ensure_ascii=False)[:1200],
            "chars": len(text), "excerpt": text[:1200], "truncated": len(text) > 1200}


class Operations:
    def __init__(self, store, host, clock=time.time):
        self.store, self.host, self.clock = store, host, clock

    def track(self, session_id, task_id):
        """Only host-supplied bindings, including silent jobs, not model-supplied IDs."""
        parts = str(task_id or "").split(":", 2)
        if session_id and len(parts) == 3 and parts[0] == "cron" and parts[1] in self.host.manifest()["jobs"]:
            self.store.write("operation_session", session_id, {"id": session_id, "job_id": parts[1], "execution_id": parts[2]})

    def checkpoint(self):
        with self.store.transaction() as db:
            row = self.store.get(db, "meta", "operation_cursor")
            if row is None:
                row = {"message_id": 0, "since": self.clock() - DAY, "execution_through": self.clock() - DAY}
                self.store.put(db, "meta", "operation_cursor", row)
            return row

    def summary(self):
        return {"checkpoint": self.store.read("meta", "operation_cursor"),
                "findings": self.store.all("operation_finding"),
                "instruction": "Use operations_read for native tool evidence; no operation audit is implied by a conversation/signal cursor."}

    def read(self, data, *, page_cursor=None, compact=False):
        cursor, now = self.checkpoint(), self.clock()
        result = {"available": True, "events": [], "executions": [], "gaps": [],
                  "scope_since": cursor["since"], "findings": [] if compact else self.store.all("operation_finding")}
        native_path = self.store.home / "state.db"
        if not native_path.exists():
            return {**result, "available": False, "gaps": ["Native session database is unavailable; no audit checkpoint advanced."]}
        jobs = self.host.manifest()["jobs"]
        roots = {s["id"] for s in self.store.all("session")} | {s["id"] for s in self.store.all("operation_session")}
        try:
            with reader(native_path) as db:
                sessions = {r["id"]: dict(r) for r in db.execute("SELECT id,parent_session_id,chat_type FROM sessions")}
                eligible = set()
                for sid in sessions:
                    lineage, current = set(), sid
                    matched, private = False, True
                    while current in sessions and current not in lineage:
                        lineage.add(current)
                        item = sessions[current]
                        private &= str(item.get("chat_type") or "").lower() not in GROUPS
                        matched |= current in roots or any(current.startswith("cron_" + jid + "_") for jid in jobs)
                        current = item.get("parent_session_id")
                    if matched and private:
                        eligible.add(sid)
                ceiling = db.execute("SELECT COALESCE(MAX(id),0) FROM messages").fetchone()[0]
                # Freeze the shared pass once; concurrent readers own separate page receipts.
                with self.store.transaction() as state:
                    cursor = self.store.get(state, "meta", "operation_cursor")
                    if "through" not in cursor:
                        cursor = {**cursor, "through": ceiling}
                        self.store.put(state, "meta", "operation_cursor", cursor)
                if page_cursor is not None:
                    cursor = page_cursor
                expected = cursor.get("through", ceiling)
                through = data.get("through", expected)
                if type(through) is not int or through != expected or not cursor["message_id"] <= through <= ceiling:
                    raise ValueError(f"Continue the frozen snapshot through {expected}; up_to is only a page checkpoint, not its boundary")
                # Scan by insertion ID: late tool results must be reviewed even when their call is older.
                end = cursor["message_id"]
                page_chars = 0
                rows = db.execute("SELECT id,session_id,role,content,tool_calls,tool_call_id,tool_name,timestamp "
                                  "FROM messages WHERE id>? AND id<=? AND timestamp>=? "
                                  "AND (role='tool' OR tool_calls IS NOT NULL) ORDER BY id",
                                  (end, through, cursor["since"]))
                for raw in rows:
                    row = dict(raw)
                    if row["session_id"] not in eligible or row["timestamp"] < cursor["since"]:
                        end = row["id"]
                        continue
                    selected = [c for c in calls(row) if not inspection(c)]
                    related = None
                    if row["role"] == "tool" and row.get("tool_call_id"):
                        candidates = db.execute("SELECT id,tool_calls FROM messages WHERE session_id=? AND id<? "
                                                "AND instr(tool_calls,?)>0 ORDER BY id DESC",
                                                (row["session_id"], row["id"], row["tool_call_id"]))
                        for candidate in candidates:
                            match = next((c for c in calls(dict(candidate)) if c.get("id") == row["tool_call_id"]), None)
                            if match:
                                related = {"message_id": candidate["id"], "call": match}
                                break
                        if related and inspection(related["call"]) and not failed_result(row.get("content")):
                            end = row["id"]
                            continue
                    if selected or row["role"] == "tool":
                        event = {"ref": "message:" + str(row["id"]), **row, "tool_calls": selected}
                        # Tool text remains untrusted evidence; never copy hidden reasoning into review context.
                        if selected:
                            event["content"] = None
                        if related:
                            event["related_call"] = related
                        if compact:
                            event = preview(event)
                        size = len(json.dumps(event, ensure_ascii=False))
                        if result["events"] and (len(result["events"]) >= 100 or page_chars + size > 64000):
                            break
                        result["events"].append(event)
                        page_chars += size
                    end = row["id"]
                else:
                    end = through
                result.update(through=through, up_to=end, more=end < through)
            ledger = self.store.home / "cron/executions.db"
            if ledger.exists():
                with reader(ledger) as db:
                    for raw in db.execute("SELECT * FROM executions ORDER BY claimed_at"):
                        row = dict(raw)
                        if row["job_id"] not in jobs:
                            continue
                        at = epoch(row.get("finished_at") or row["claimed_at"])
                        if cursor["execution_through"] < at <= now:
                            result["executions"].append({"ref": "execution:" + row["id"], **row})
            else:
                result["gaps"].append("Native Cron execution ledger is unavailable; execution coverage is unverified.")
        except (sqlite3.Error, KeyError, TypeError, ValueError) as exc:
            return {**result, "available": False, "gaps": result["gaps"] + [f"Native evidence read failed: {type(exc).__name__}: {exc}"]}
        refs = [r["ref"] for r in result["events"] + result["executions"]]
        snapshot = {"cursor": cursor, "up_to": result["up_to"], "through": through, "execution_through": now,
                    "refs": refs, "gaps": result["gaps"]}
        token = digest(json.dumps(snapshot, sort_keys=True))
        with self.store.transaction() as db:
            # Receipts contain references, not transcripts. Keep them for interrupted reviewers.
            for old in self.store.rows(db, "operation_snapshot"):
                if old["execution_through"] < now - 7 * DAY:
                    self.store.delete(db, "operation_snapshot", old["token"])
            self.store.put(db, "operation_snapshot", token, {**snapshot, "token": token})
        return {**result, "token": token, "instruction": "Inspect intent and actual state, save findings first, then operations_complete(token). Continue through this snapshot while more=true. Calls/receipts are observations, not proof of correctness or authority. Missing, pruned, unpersisted and pre-scope history is not covered."}

    def complete(self, data):
        with self.store.transaction() as db:
            snapshot = self.store.get(db, "operation_snapshot", data.get("token"), {})
            if not snapshot:  # Finish a page issued before the upgrade without resetting its cursor.
                snapshot = self.store.get(db, "meta", "operation_snapshot", {})
            current = self.store.get(db, "meta", "operation_cursor")
            if (not snapshot or data.get("token") != snapshot.get("token") or not current
                    or current["since"] != snapshot["cursor"]["since"]
                    or current["message_id"] < snapshot["cursor"]["message_id"]):
                raise ValueError("Stale or unknown operation snapshot; read again")
            if snapshot["gaps"]:
                raise ValueError("Evidence coverage is incomplete; preserve the checkpoint and resolve the gap")
            bounded(data.get("summary"), 2000)
            duplicate = current["message_id"] >= snapshot["up_to"]
            updated = {**current, "message_id": max(current["message_id"], snapshot["up_to"]),
                       "execution_through": max(current["execution_through"], snapshot["execution_through"])}
            boundary = current.get("through", snapshot["through"])
            more = updated["message_id"] < boundary
            if more:
                updated["through"] = boundary
            else:
                updated.pop("through", None)
            self.store.put(db, "meta", "operation_cursor", updated)
            return {"reviewed": True, "already_reviewed": duplicate, "checkpoint": updated, "more": more, "through": boundary,
                    "instruction": "Only this page is reviewed. Call operations_read with data={} now; the remaining snapshot is preserved automatically." if more else "The operation snapshot is reviewed; future arrivals belong to the next pass."}

    def evidence(self, data):
        """Read only references issued to an audit page, without copying a transcript to plugin state."""
        token = data.get("receipt")
        snapshot = self.store.read("operation_snapshot", token, {})
        if not snapshot or snapshot["execution_through"] < self.clock() - 7 * DAY:
            raise ValueError("Audit page expired or unknown; ask the parent to reread its batch")
        ref = data.get("ref")
        if ref is not None and ref not in snapshot["refs"]:
            raise ValueError("Evidence must belong to the assigned audit receipt")
        events, missing = [], []
        with reader(self.store.home / "state.db") as db:
            for item in snapshot["refs"]:
                if not item.startswith("message:") or ref is not None and item != ref:
                    continue
                row = db.execute("SELECT id,session_id,role,content,tool_calls,tool_call_id,tool_name,timestamp FROM messages WHERE id=?", (int(item.split(":")[1]),)).fetchone()
                if row is None:
                    missing.append(item)
                    continue
                row = dict(row)
                row["ref"] = item
                row["tool_calls"] = [c for c in calls(row) if not inspection(c)]
                if row["role"] == "assistant":
                    row["content"] = None  # Never expose reasoning from tool-bearing assistant rows.
                if row.get("tool_call_id"):
                    for candidate in db.execute("SELECT id,tool_calls FROM messages WHERE session_id=? AND id<? AND instr(tool_calls,?)>0 ORDER BY id DESC", (row["session_id"], row["id"], row["tool_call_id"])):
                        match = next((c for c in calls(dict(candidate)) if c.get("id") == row["tool_call_id"]), None)
                        if match:
                            row["related_call"] = {"message_id": candidate["id"], "call": match}
                            break
                # Context for a page boundary: original turn text is evidence, not new authority.
                user = db.execute("SELECT id,content FROM messages WHERE session_id=? AND id<? AND role='user' ORDER BY id DESC LIMIT 1", (row["session_id"], row["id"])).fetchone()
                if user:
                    row["user_context"] = dict(user)
                events.append(row)
        executions = []
        ledger = self.store.home / "cron/executions.db"
        execution_refs = [r for r in snapshot["refs"] if r.startswith("execution:") and (ref is None or r == ref)]
        if execution_refs and ledger.exists():
            with reader(ledger) as db:
                for item in execution_refs:
                    row = db.execute("SELECT * FROM executions WHERE id=?", (item.split(":", 1)[1],)).fetchone()
                    if row:
                        executions.append({"ref": item, **dict(row)})
                    else:
                        missing.append(item)
        elif execution_refs:
            missing.extend(execution_refs)
        if ref is None:
            return {"events": [preview(e) for e in events], "executions": executions, "missing": missing,
                    "instruction": "This is an evidence index. Expand truncated entries needed to verify intent, effects, failures or promises via the same receipt and ref. Group related calls/results; harmless known read-only inspections need no body replay. Never call a preview a full evidence review."}
        text = json.dumps((events + executions)[0], ensure_ascii=False) if events or executions else ""
        offset, length = data.get("offset", 0), data.get("length", 12000)
        if type(offset) is not int or offset < 0 or type(length) is not int or not 1 <= length <= 24000:
            raise ValueError("Use a nonnegative offset and length 1..24000")
        return {"ref": ref, "text": text[offset:offset + length], "offset": offset,
                "next_offset": offset + length if offset + length < len(text) else None, "total_chars": len(text), "missing": missing}

    def finding(self, data):
        with self.store.transaction() as db:
            snapshot = self.store.get(db, "meta", "operation_snapshot", {})
            refs_seen = set(snapshot.get("refs", []))
            for receipt in self.store.rows(db, "operation_snapshot"):
                if receipt["execution_through"] >= self.clock() - 7 * DAY:
                    refs_seen.update(receipt["refs"])
            key = data.get("id")
            old = self.store.get(db, "operation_finding", key, {}) if key else {}
            if key and not old:
                raise ValueError("Unknown finding")
            refs = data.get("evidence", old.get("evidence", []))
            if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or r not in refs_seen | set(old.get("evidence", [])) for r in refs):
                raise ValueError("Finding needs evidence references returned by operations_read")
            key = key or digest("|".join(sorted(refs)))
            if self.store.get(db, "forgotten", "operation_finding:" + key):
                raise ValueError("This finding was explicitly forgotten; do not recreate it")
            previous = self.store.get(db, "operation_finding", key, old)
            row = {**previous, "id": key, "evidence": refs, "updated": self.clock()}
            for field in ("summary", "impact", "verification", "disclosure", "no_notice_reason"):
                if field in data:
                    row[field] = bounded(data[field], 4000)
            if not row.get("summary") or not row.get("impact"):
                raise ValueError("Finding needs a factual summary and impact")
            row["status"] = data.get("status", row.get("status", "open"))
            if row["status"] not in {"open", "repairing", "resolved", "dismissed"}:
                raise ValueError("Invalid finding status")
            if row["status"] in {"resolved", "dismissed"} and (not row.get("verification") or not (row.get("disclosure") or row.get("no_notice_reason"))):
                raise ValueError("Closure requires verification and disclosure evidence or a reason no notice is needed")
            self.store.put(db, "operation_finding", key, row)
            return row
