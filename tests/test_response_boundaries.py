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
            ('goal_update', {'id':'g','progress': ['x'*300000], 'warning':'Goal committed; watch cleanup failed'}, {'id': 'g'}, 'goal', 'g'),
            ('notification_prepare', {'id': 'n', 'sources': ['x'*300000], 'final_response': 'Approved previous notice'}, {}, 'notice', 'n'),
        ):
            with self.subTest(action=action):
                reply = json.loads(Runtime._response(result, action=action, data=data))
                self.assertTrue(reply['ok'])
                self.assertEqual(reply['result']['content_ref']['data'], {'kind': kind, 'id': key})
                for field in ('partial', 'requires_host_action', 'final_response', 'warning'):
                    if field in result:
                        self.assertEqual(reply['result'][field], result[field])

    def test_final_envelope_and_recovered_fields_share_budget(self):
        result = {'blocked_topics': ['']}
        size = len(Runtime._response(result).encode())
        result['blocked_topics'] = ['x' * (256 * 1024 - size - 10)]
        self.assertLess(len(Runtime._response(result).encode()), 256 * 1024)
        envelope = {'ok': True, 'result': result, 'revision': 'r' * 64, 'recovered': True}
        raw = Runtime._receipt(envelope, action='preferences')
        reply = json.loads(raw)
        self.assertLessEqual(len(raw.encode()), 256 * 1024)
        self.assertEqual(reply['revision'], envelope['revision'])
        self.assertTrue(reply['recovered'])
        self.assertEqual(reply['result']['content_ref']['data'], {'kind': 'preferences', 'id': 'current'})
        self.assertEqual(Runtime._receipt(reply, action='preferences'), raw)

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
