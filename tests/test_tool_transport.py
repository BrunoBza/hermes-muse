import tempfile
import unittest
from pathlib import Path
from test_companion import prepare, Host
from hermes_muse.responses import preflight
from hermes_muse.content_io import DomainError
from hermes_muse.conversation import page
from hermes_muse.context_pages import context
from hermes_muse.service import Companion


class ToolTransportTests(unittest.TestCase):
    def test_control_and_content_bounds_before_work(self):
        for args in (
            {'action': 'context', 'data': {'window': 'x'*2000}},
            {'action': 'review_complete', 'data': {'job': 'feed-pulse', 'window': 'short'}},
            {'action': 'content_write', 'data': {'body': 'x'*60001}},
            {'action': 'research_start', 'data': {'items': ['x'*2001]}},
            {'action': 'watch_create', 'data': {'prompt': 'x'*4001}},
        ):
            with self.subTest(action=args['action']), self.assertRaises(DomainError):
                preflight(args)

    def test_large_allocation_links_original_native_evidence(self):
        import json
        from hermes_muse.runtime import Runtime
        reply = json.loads(Runtime._response({'token': 'receipt', 'events': ['x'*300000]}, action='operations_read'))
        self.assertEqual(reply['result']['content_ref'], {'action': 'operations_evidence', 'data': {'receipt': 'receipt', 'offset': 0, 'limit': 25}})
        self.assertTrue(reply['result']['result_is_reference'])

    def test_unreturnable_conversation_does_not_record_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = prepare(Path(tmp))
            state = {'available': True, 'session_id': 's', 'revision': 'r',
                     'messages': [{'id': 'x'*300000, 'role': 'user', 'text': 'Body'}]}
            with self.assertRaises(DomainError):
                page(store, state, {'revision': 'r', 'offset': 0}, 1800000000)
            self.assertFalse(store.all('conversation_window'))

    def test_unreturnable_signal_does_not_mark_body_served(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = prepare(Path(tmp))
            service = Companion(store, Host(), lambda: 1800000000)
            store.write('signal', 's', {'id': 's', 'session_id': 'x'*300000,
                                      'text': 'Body', 'created': 1799999999})
            index = context(service, {'section': 'signals', 'job': 'memory-upkeep'})
            with self.assertRaises(DomainError):
                context(service, {'section': 'signals', 'job': 'memory-upkeep', 'window': index['window'], 'id': 's'})
            self.assertEqual(store.read('review_window', index['window'])['served'], {})
