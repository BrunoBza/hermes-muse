"""Resolve evidence from current-profile persisted facts, never model owner claims."""

import sqlite3
from .content_io import DomainError, revision
from .views import Views
from .store import DAY


def resolve(service, refs, goal):
    if not isinstance(refs, list) or not 1 <= len(refs) <= 20:
        raise DomainError("invalid_argument", "Use 1..20 structured evidence_refs")
    result = []
    size = 0
    for ref in refs:
        if not isinstance(ref, dict):
            raise DomainError("invalid_argument", "Evidence ref must be an object")
        kind = ref.get("kind")
        text = ""
        source_tool = None
        if kind == "muse_object":
            if set(ref) - {"kind", "object_kind", "id", "resource", "revision"}:
                raise DomainError(
                    "invalid_argument", "Unsupported artifact reference fields"
                )
            if ref.get("object_kind") == "goal_file" and ref.get("id") != goal["id"]:
                raise DomainError(
                    "permission_denied", "Artifact belongs to another goal"
                )
            if ref.get("object_kind") not in {"goal_file", "review_report", "feed"}:
                raise DomainError(
                    "permission_denied", "Verification needs a task artifact"
                )
            body, meta, current = Views(service.store.home).object(
                ref["object_kind"], ref["id"], ref.get("resource")
            )
            if ref.get("revision") != current:
                raise DomainError(
                    "revision_conflict",
                    "Evidence artifact changed",
                    current_revision=current,
                )
            if ref["object_kind"] == "feed" and meta.get("goal_id") != goal["id"]:
                raise DomainError("permission_denied", "Feed is outside this goal")
            text = body or ""
            provenance = "artifact_observed"
        elif kind == "user_report":
            if set(ref) - {"kind", "signal_id", "quote"}:
                raise DomainError(
                    "invalid_argument", "Unsupported report reference fields"
                )
            signal = (
                Views(service.store.home).record("signal", ref.get("signal_id")) or {}
            )
            text = ref.get("quote", "")
            if (
                signal.get("session_id") != goal.get("session_id")
                or not isinstance(text, str)
                or not text.strip()
                or text not in signal.get("text", "")
                or signal.get("created", 0) < service.clock() - DAY
            ):
                raise DomainError(
                    "permission_denied",
                    "Report must quote a recent original user signal",
                )
            provenance = "user_reported"
        elif kind == "native_message":
            if set(ref) - {"kind", "session_id", "message_id", "hash"}:
                raise DomainError(
                    "invalid_argument", "Unsupported native reference fields"
                )
            if (
                ref.get("session_id") != goal.get("session_id")
                or type(ref.get("message_id")) is not int
            ):
                raise DomainError(
                    "permission_denied",
                    "Native message must belong to the goal session",
                )
            path = service.store.home / "state.db"
            if path.is_symlink() or not path.is_file():
                raise DomainError("source_unavailable", "Native history unavailable")
            db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
            try:
                db.execute("PRAGMA query_only=ON")
                row = db.execute(
                    "SELECT role,content,tool_name,tool_call_id FROM messages WHERE id=? AND session_id=?",
                    (ref["message_id"], ref["session_id"]),
                ).fetchone()
            finally:
                db.close()
            if not row or row[0] not in {"tool", "assistant"}:
                raise DomainError(
                    "permission_denied", "Native result/reply unavailable"
                )
            text = row[1] or ""
            source_tool = row[2] if row[0] == "tool" else None
            if row[0] == "tool" and not row[3]:
                raise DomainError(
                    "source_unavailable", "Native tool result lacks correlation"
                )
            if ref.get("hash") and ref["hash"] != revision(text.encode()):
                raise DomainError("revision_conflict", "Native message hash changed")
            provenance = "tool_observed" if row[0] == "tool" else "artifact_observed"
        else:
            raise DomainError("invalid_argument", "Unknown evidence kind")
        size += len(text.encode())
        if size > 256 * 1024:
            raise DomainError(
                "size_limit",
                "Evidence exceeds bounded verification budget; preserve partial",
            )
        result.append(
            {
                "ref": ref,
                "provenance": provenance,
                "source_tool": source_tool,
                "observed_at": service.clock(),
                "content_hash": revision(text.encode()),
            }
        )
    return result
