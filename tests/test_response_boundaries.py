import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_companion import prepare, Host
from hermes_muse.runtime import Runtime
from hermes_muse.service import Companion
from hermes_muse.content_io import DomainError


class ResponseBoundaryTests(unittest.TestCase):
    def test_large_success_references_keep_control_fields(self):
        for action, result, data, kind, key in (
            ('preferences', {'blocked_topics': ['x'*300000]}, {}, 'preferences', 'current'),
            ('installation_prepare', {'pending_evidence': ['x'*300000], 'partial': True, 'requires_host_action': True}, {}, 'installation', 'current'),
            ('run_complete', {'id': 'r', 'gaps': ['x'*300000]}, {}, 'run', 'r'),
            ('followup_update', {'summary': 'x'*300000}, {'goal_id': 'g'}, 'goal', 'g'),
            ('notification_prepare', {'id': 'n', 'sources': ['x'*300000], 'final_response': 'Approved previous notice'}, {}, 'notice', 'n'),
        ):
            with self.subTest(action=action):
                reply = json.loads(Runtime._response(result, action=action, data=data))
                self.assertTrue(reply['ok'])
                self.assertEqual(reply['result']['content_ref']['data'], {'kind': kind, 'id': key})
                for field in ('partial', 'requires_host_action', 'final_response'):
                    if field in result:
                        self.assertEqual(reply['result'][field], result[field])

    def test_oversized_delivery_rejected_before_reserving_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = prepare(Path(tmp))
            service = Companion(store, Host(), lambda: 1800000000)
            notice = service.notification_add({'event_key': 'large', 'message': 'Synthetic',
                'rationale': 'Fixture', 'sources': ['x'*2000]*150, 'verified_at': 1800000000,
                'expires': 1800003600})
            with patch.object(service, 'conversation_block', return_value=None), patch.object(service, 'delivery_gate', return_value={'blocked_by': []}):
                with self.assertRaises(DomainError) as error:
                    service.notification_queue({'id': notice['id']}, delivery={'execution_id': 'attempt', 'job_id': 'patrol'})
            self.assertEqual(error.exception.code, 'size_limit')
            row = store.read('notification', notice['id'])
            self.assertEqual(row['status'], 'pending')
            self.assertNotIn('execution_id', row)
            self.assertFalse(store.all('budget'))

    def test_unaddressable_review_rejects_before_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = prepare(Path(tmp))
            service = Companion(store, Host(), lambda: 1800000000)
            original = {'id': 'candidate', 'revision': 1, 'goal_ids': ['x'*300000]}
            store.write('followup_turn', 'candidate', original)
            with self.assertRaises(DomainError):
                service.followups.review({'candidate_id': 'candidate', 'expected_revision': 1,
                    'disposition': 'no_commitment', 'reason': 'Synthetic'})
            self.assertEqual(store.read('followup_turn', 'candidate'), original)
