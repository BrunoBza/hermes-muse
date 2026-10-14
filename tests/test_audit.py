import json
import unittest

from hermes_muse.audit import Audit
from test_operations import OperationFixture


class AuditTests(OperationFixture):
    def setUp(self):
        super().setUp()
        from unittest.mock import patch
        routing = patch('hermes_muse.delegation.settings', return_value={})
        routing.start(); self.addCleanup(routing.stop)

    def test_parallel_slots_are_disjoint_and_out_of_order_results_cannot_skip(self):
        for n in range(130):
            self.call(str(n), args={'path': str(n), 'body': 'x' * 6000})
        audit = Audit(self.ops)
        batch = audit.batch()
        self.assertEqual(3, len(batch['assignments']))
        wave = self.store.read('meta', 'operation_wave')
        refs = [set(self.store.read('operation_snapshot', p['receipt'])['refs']) for p in wave['pages']]
        self.assertFalse(refs[0] & refs[1] or refs[1] & refs[2] or refs[0] & refs[2])
        # Parent only receives assignments, not the raw payloads.
        self.assertNotIn('x' * 100, json.dumps(batch))
        later = audit.commit({'batch': batch['batch'], 'reviews': [{'slot': 2, 'summary': 'Verified page two'}]})
        self.assertEqual(0, later['checkpoint']['message_id'])
        self.assertEqual([1, 3], [a['slot'] for a in audit.batch()['assignments']])
        audit.commit({'batch': batch['batch'], 'reviews': [{'slot': 1, 'summary': 'Verified page one'}]})
        self.assertEqual(wave['pages'][1]['up_to'], self.ops.checkpoint()['message_id'])
        audit.commit({'batch': batch['batch'], 'reviews': [{'slot': 3, 'summary': 'Verified page three'}]})
        self.assertTrue(self.store.read('meta', 'operation_wave')['done'])

    def test_evidence_expansion_preserves_complete_body_and_hides_reasoning(self):
        self.message(role='user', text='Inspect this file, do not change it')
        self.call('read', name='read_file', args={'path': 'example'})
        result = self.message(role='tool', text='head' + 'x' * 30000 + 'ACTUAL ERROR AT END', call_id='read')
        batch = Audit(self.ops).batch()
        receipt = self.store.read('meta', 'operation_wave')['pages'][0]['receipt']
        index = self.ops.evidence({'receipt': receipt})
        self.assertTrue(any(e['truncated'] for e in index['events']))
        pieces, offset = [], 0
        while offset is not None:
            part = self.ops.evidence({'receipt': receipt, 'ref': f'message:{result}', 'offset': offset})
            pieces.append(part['text']);offset = part['next_offset']
        body = json.loads(''.join(pieces))
        self.assertTrue(body['content'].endswith('ACTUAL ERROR AT END'))
        self.assertIn('do not change', body['user_context']['content'])
        self.assertEqual('read_file', body['related_call']['call']['function']['name'])
        with self.assertRaises(ValueError):
            self.ops.evidence({'receipt': receipt, 'ref': 'message:999999'})

    def test_resuming_batch_does_not_allocate_again_or_require_model_tokens(self):
        self.call()
        audit = Audit(self.ops)
        batch = audit.batch()
        self.now += 10
        resumed = Audit(self.ops).batch()
        self.assertGreater(resumed.pop("observed_at"), batch.pop("observed_at"))
        self.assertEqual(batch, resumed)
        result = audit.commit({'batch': batch['batch'], 'reviews': [{'slot': 1, 'summary': 'Verified original request and result'}]})
        self.assertFalse(result['more'])
        self.assertFalse(audit.commit({'batch': batch['batch'], 'reviews': [{'slot': 1, 'summary': 'Retry acknowledgement'}]})['more'])
        with self.assertRaises(ValueError):
            audit.commit({'batch': 999, 'reviews': [{'slot': 1, 'summary': 'Wrong batch'}]})

    def test_missing_native_evidence_is_a_gap_not_a_clean_review(self):
        self.call()
        batch = Audit(self.ops).batch()
        receipt = self.store.read('meta', 'operation_wave')['pages'][0]['receipt']
        self.db.execute('DELETE FROM messages');self.db.commit()
        self.assertTrue(self.ops.evidence({'receipt': receipt})['missing'])
        with self.assertRaisesRegex(ValueError, 'missing'):
            Audit(self.ops).commit({'batch': batch['batch'], 'reviews': [{'slot': 1, 'summary': 'Cannot verify deleted native evidence'}]})


    def test_active_and_unknown_receipts_never_launch_another_worker(self):
        self.call()
        audit = Audit(self.ops)
        batch = audit.batch()
        request = {'tasks':[batch['assignments'][0]['task']]}
        calls = []
        result = audit.dispatch(request, lambda: calls.append('launch') or {'status':'dispatched','delegation_id':'original'}, session_id='parent', tool_call_id='call')
        self.assertEqual(result['delegation_id'],'original')
        with self.assertRaisesRegex(ValueError,'original dispatch'):
            audit.dispatch(request, lambda: calls.append('duplicate') or {})
        saved = audit.batch()
        self.assertFalse(saved['assignments'])
        self.assertEqual(saved['pending_owners'][0]['owner_id'],'original')
        self.assertEqual(calls,['launch'])


if __name__ == '__main__':
    unittest.main()
