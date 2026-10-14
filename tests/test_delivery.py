import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_companion import prepare, Host
from hermes_muse.service import Companion
from hermes_muse.delivery import apply_notice
from hermes_muse.followup import snapshot
from hermes_muse.store import digest


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.store = prepare(self.home)
        self.now = 1800000000
        self.service = Companion(self.store, Host(), lambda: self.now)
        self.service.signal("signal", "origin", "Research the accepted goal")
        self.service.goal_create(
            {
                "id": "g",
                "title": "Fixture",
                "description": "Work",
                "completion_criteria": "Verified result",
                "signal_id": "signal",
            }
        )
        goal, body = self.store.goal("g")
        goal["followup"].update(
            result_state="verified",
            verification={
                "verified_at": self.now,
                "summary": "Verified original task result",
                "sources": ["fixture:result"],
            },
        )
        self.store.save_goal(goal, body)
        self.notice = {
            "id": "n",
            "goal_id": "g",
            "final_result": True,
            "followup_scope_revision": 1,
            "followup_verified_at": self.now,
            "status": "unknown",
        }
        self.store.write("notification", "n", self.notice)

    def fu(self):
        return self.store.goal("g")[0]["followup"]

    def test_unknown_basis_suppresses_ticks_without_confirming_or_sending(self):
        self.assertTrue(apply_notice(self.store, self.notice, self.now))
        current = self.fu()["revision"]
        for n in range(10):
            self.assertFalse(apply_notice(self.store, self.notice, self.now + n * 1800))
            self.assertEqual(
                snapshot(self.home, now=self.now + n * 1800)["due_total"], 0
            )
        self.assertEqual(self.fu()["revision"], current)
        self.assertEqual(self.fu()["delivery_state"], "unknown")
        self.assertEqual(len(self.store.all("notification")), 1)
        goal, body = self.store.goal("g")
        goal["followup"]["verification"]["verified_at"] += 1
        self.store.save_goal(goal, body)
        self.assertEqual(snapshot(self.home, now=self.now + 4000)["due_total"], 1)

    def test_notice_evidence_survives_cas_conflict_and_replays_once(self):
        self.notice["status"] = "sent"
        self.store.write("notification", "n", self.notice)
        with patch.object(
            self.store, "save_goal", side_effect=ValueError("Concurrent edit")
        ):
            self.assertFalse(apply_notice(self.store, self.notice, self.now))
        self.assertEqual(self.store.read("notification", "n")["status"], "sent")
        self.assertTrue(apply_notice(self.store, self.notice, self.now))
        rev = self.fu()["revision"]
        self.assertFalse(apply_notice(self.store, self.notice, self.now + 1))
        self.assertEqual(self.fu()["revision"], rev)
        self.assertEqual(self.fu()["delivery_state"], "confirmed")
        self.service.goal_update(
            {"id": "g", "status": "cancelled", "signal_id": "signal"}
        )
        self.assertFalse(apply_notice(self.store, self.notice, self.now + 2))
        self.assertEqual(self.store.goal("g")[0]["status"], "cancelled")

    def test_unsent_candidate_does_not_claim_unknown_and_queued_stalls_once(self):
        self.notice["status"] = "candidate"
        self.assertFalse(apply_notice(self.store, self.notice, self.now))
        self.assertEqual(self.fu()["delivery_state"], "open")
        self.notice["status"] = "queued"
        self.store.write("notification", "n", self.notice)
        self.assertTrue(apply_notice(self.store, self.notice, self.now))
        self.assertTrue(apply_notice(self.store, self.notice, self.now + 86401))
        self.assertEqual(self.fu()["blocker_class"], "review_required")
        rev = self.fu()["revision"]
        self.assertFalse(apply_notice(self.store, self.notice, self.now + 200000))
        self.assertEqual(self.fu()["revision"], rev)
        self.assertEqual(self.fu()["delivery_state"], "queued")

    def test_unrelated_persisted_reply_cannot_form_basis(self):
        goal, _ = self.store.goal("g")
        fu = goal["followup"]
        text = "Hello, how are you?"
        self.store.write(
            "followup_reply",
            "reply",
            {
                "id": "reply",
                "session_id": "origin",
                "observed_at": self.now,
                "assistant_hash": digest(text),
                "message_id": 42,
            },
        )
        self.service.host.conversation = lambda *args: {
            "messages": [{"id": 42, "role": "assistant", "text": text}]
        }
        with self.assertRaisesRegex(ValueError, "does not contain"):
            self.service.followups.update(
                {
                    "kind": "handoff",
                    "goal_id": "g",
                    "expected_revision": fu["revision"],
                    "reply_id": "reply",
                    "reason": "Unrelated greeting",
                },
                session_id="origin",
                turn_id="signal",
            )
        self.assertIsNone(self.fu().get("delivery_basis"))

    def test_legacy_notice_and_reply_basis_are_only_in_memory(self):
        goal, body = self.store.goal("g")
        goal["followup"].update(delivery_state="unknown", notice_id="n")
        self.store.save_goal(goal, body)
        before = (self.home / "muse/workspace/goals/g/GOAL.md").read_bytes()
        self.assertEqual(snapshot(self.home, now=self.now)["due_total"], 0)
        self.assertEqual((self.home / "muse/workspace/goals/g/GOAL.md").read_bytes(), before)
        goal["followup"].update(notice_id=None, reply_id="reply")
        self.store.save_goal(goal, body)
        text = goal["followup"]["verification"]["summary"]
        self.store.write("followup_reply", "reply", dict(id="reply", session_id="origin",
                         observed_at=self.now, message_id=42, assistant_hash=digest(text)))
        history = {"messages": [dict(id=42, role="assistant", text=text)]}
        with patch("hermes_muse.conversation.read_conversation", return_value=history):
            for n in range(10):
                self.assertEqual(snapshot(self.home, now=self.now + n * 1800)["due_total"], 0)
        self.assertIsNone(self.fu().get("delivery_basis"))
        with patch("hermes_muse.conversation.read_conversation", return_value={"messages": []}):
            self.assertEqual(snapshot(self.home, now=self.now)["due_total"], 1)
