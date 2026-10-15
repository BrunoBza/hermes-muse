"""Replayable projection of persisted delivery evidence into goal metadata."""


def basis(fu, kind, ref, status, now):
    return {
        "kind": kind,
        "ref": ref,
        "scope_revision": fu["scope_revision"],
        "verified_at": fu.get("verification", {}).get("verified_at"),
        "status": status,
        "noted_at": now,
    }


def valid_basis(fu, records):
    b = fu.get("delivery_basis") or {}
    if b.get("scope_revision") != fu["scope_revision"] or b.get(
        "verified_at"
    ) != fu.get("verification", {}).get("verified_at"):
        return False
    kind = "followup_reply" if b.get("kind") == "reply" else "notification"
    row = next((r for r in records.get(kind, []) if r["id"] == b.get("ref")), None)
    return bool(
        row and (kind == "followup_reply" or row.get("status") == b.get("status"))
    )



def denies_delivery(text):
    """A contradiction veto, never a positive natural-language delivery classifier."""
    import re
    return bool(re.search(r"(?i)(\bnot ready\b|\b(?:not|never|haven't|hasn't) delivered\b|尚未准备好|没有交付|尚未交付|还未交付|未完成交付)", text))


def reply_evidence(goal, reply, history):
    """Same original-text and version checks for new handoffs and legacy projections."""
    from .store import digest
    fu = goal["followup"]
    verification = fu.get("verification", {})
    from .content_io import revision
    from .views import canonical
    historical = reply.get('historical_binding') == {'goal_id': goal['id'], 'scope_revision': fu['scope_revision'],
        'verification_revision': revision(canonical(verification))}
    if (reply.get("session_id") != goal.get("session_id")
            or reply.get("observed_at", 0) < max(fu.get("source_created_at", goal["created"]),
                                                0 if historical else verification.get("verified_at", 0))):
        return False, False
    matches = [m for m in history.get("messages", [])
               if m.get("role") == "assistant" and m.get("id") == reply.get("message_id")
               and digest(m.get("text", "")) == reply.get("assistant_hash")]
    text = matches[0].get("text", "") if len(matches) == 1 else ""
    refs = [entry.get("ref", {}).get("resource") or entry.get("ref", {}).get("id")
            or "message:" + str(entry.get("ref", {}).get("message_id", ""))
            for entry in verification.get("evidence_refs", [])]
    relevant = bool(text and not denies_delivery(text) and reply.get("message_id") and (
        historical or verification.get("summary") and verification["summary"] in text
        or any(isinstance(ref, str) and len(ref) >= 8 and ref in text for ref in refs)))
    return bool(text), relevant


def handoff_review(goal, reply, now):
    """Receipt of the parent's explicit semantic handoff action, not text inference."""
    from .views import canonical
    from .content_io import revision
    fu = goal['followup']
    return {'id': goal['id'], 'reply_id': reply['id'], 'session_id': goal['session_id'],
            'scope_revision': fu['scope_revision'], 'verification_revision': revision(canonical(fu.get('verification', {}))),
            'assistant_hash': reply['assistant_hash'], 'message_id': reply['message_id'], 'reviewed_at': now}


def reviewed_reply(goal, reply, history, review):
    """Replay only a reviewed, unchanged original final reply for this result version."""
    if not isinstance(review, dict) or not reply.get('message_id'):
        return False
    expected = handoff_review(goal, reply, review.get('reviewed_at'))
    if review != expected or not history.get('available'):
        return False
    from .store import digest
    return sum(m.get('role') == 'assistant' and m.get('id') == reply.get('message_id')
               and digest(m.get('text', '')) == reply.get('assistant_hash') and not denies_delivery(m.get('text', ''))
               for m in history.get('messages', [])) == 1


def inferred_basis(home, goal, records, now):
    """Optional legacy field stays in memory: never migrate GOALs during a read."""
    fu = goal["followup"]
    if fu.get("delivery_basis") or fu.get("result_state") != "verified":
        return None
    notice = next((r for r in records.get("notification", []) if r["id"] == fu.get("notice_id")), None)
    if (notice and notice.get("goal_id") == goal["id"] and notice.get("final_result")
            and notice.get("followup_scope_revision") == fu["scope_revision"]
            and notice.get("followup_verified_at") == fu.get("verification", {}).get("verified_at")
            and notice.get("status") in {"unknown", "failed", "cancelled", "queued", "dispatching", "transport_queued"}):
        return basis(fu, "notice", notice["id"], notice["status"], now)
    reply = next((r for r in records.get("followup_reply", []) if r["id"] == fu.get("reply_id")), None)
    if reply and reply.get("session_id") == goal.get("session_id"):
        from .views import Views
        from .followup_recovery import exact_reply
        review = Views(home).record('followup_handoff', goal['id'])
        if not review:
            return None
        resolved, history = exact_reply(home, reply, since=fu.get('source_created_at', goal['created']))
        if review and resolved and reviewed_reply(goal, resolved, history, review):
            return basis(fu, "reply", reply["id"], "recorded_unconfirmed", now)
    return None

def apply_notice(store, notice, now):
    if (
        not notice.get("goal_id")
        or not notice.get("final_result")
        or notice.get("status")
        not in {
            "sent",
            "queued",
            "dispatching",
            "transport_queued",
            "unknown",
            "failed",
            "cancelled",
        }
    ):
        return False
    try:
        with store.transaction():
            goal, body, fingerprint = store.goal(
                notice["goal_id"], with_fingerprint=True
            )
            fu = goal.get("followup") or {}
            if not fu or fu.get("result_state") != "verified":
                return False
            if (
                goal["status"] == "cancelled"
                or fu.get("delivery_state") == "suppressed"
                or fu.get("scope_revision") != notice.get("followup_scope_revision")
                or fu.get("verification", {}).get("verified_at")
                != notice.get("followup_verified_at")
                or fu.get("notice_id") not in {None, notice["id"]}
            ):
                return False
            b = basis(fu, "notice", notice["id"], notice["status"], now)
            previous = fu.get("delivery_basis") or {}
            if all(previous.get(k) == v for k, v in b.items() if k != "noted_at"):
                if (
                    fu.get("delivery_state") != "queued"
                    or fu.get("next_check_at", 0) > now
                    or fu.get("blocker_class") == "review_required"
                ):
                    return False
                checks = fu.get("delivery_checks", 0) + 1
                stalled = now - previous.get("noted_at", now) >= 86400
                fu.update(
                    delivery_checks=checks,
                    next_check_at=now
                    + (1800 if checks == 1 else 7200 if checks == 2 else 28800),
                    blocker_class="review_required" if stalled else None,
                    delivery_note="Delivery stalled; await changed transport evidence, never resend"
                    if stalled
                    else "Awaiting native transport evidence",
                    revision=fu["revision"] + 1,
                )
                store.save_goal(goal, body, expected_hash=fingerprint)
                return True
            state = (
                "confirmed"
                if notice["status"] == "sent"
                else "queued"
                if notice["status"] in {"queued", "dispatching", "transport_queued"}
                else "unknown"
            )
            fu.update(
                delivery_state=state,
                delivery_basis=b,
                notice_id=notice["id"],
                revision=fu["revision"] + 1,
                next_check_at=now + 1800,
                blocker_class="delivery_unknown" if state == "unknown" else None,
            )
            if state == "confirmed":
                fu["delivery_ref"] = {
                    k: notice.get(k) for k in ("id", "job_id", "execution_id")
                }
            store.save_goal(goal, body, expected_hash=fingerprint)
            return True
    except (ValueError, OSError):
        # Notification evidence remains authoritative and is replayed next maintenance pass.
        return False
