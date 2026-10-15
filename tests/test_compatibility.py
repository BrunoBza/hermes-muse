"""Synthetic compatibility paths and completeness invariants, no live profiles."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_companion import prepare, Host
from hermes_muse.service import Companion
from hermes_muse.store import digest
from hermes_muse.conversation import previews, page, PREVIEW_MESSAGES, PREVIEW_CHARS, PAGE_CHARS
from hermes_muse.delegation import dispatch, concurrency_limit
from hermes_muse.audit import Audit


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = prepare(self.temp.name)
        self.now = 1800000000
        self.host = Host()
        self.service = Companion(self.store, self.host, lambda: self.now)

    def state(self, sid, texts):
        messages = [{'id': n+1, 'role': 'user', 'text': t, 'at': self.now-10} for n,t in enumerate(texts)]
        return {'session_id': sid, 'available': True, 'messages': messages,
                'revision': digest(json.dumps(messages, sort_keys=True))}

    def test_preview_keeps_latest_and_full_cancel_tail_is_recoverable(self):
        texts = ['Old accepted promise, keep its full scope.'] + ['chat '+str(n) for n in range(40)]
        texts += ['x'*30000 + 'Cancel only the first scope; keep second open.']
        state = self.state('main', texts)
        self.store.write('session', 'main', {'id':'main'})
        self.host.conversation = lambda sid,since: copy.deepcopy(state)
        preview = self.service.conversation_states(served=True)['main']
        self.assertLessEqual(len(preview['messages']), PREVIEW_MESSAGES)
        self.assertLessEqual(sum(len(m['text']) for m in preview['messages']), PREVIEW_CHARS)
        self.assertEqual(preview['messages'][-1]['id'], len(texts))
        self.assertFalse(preview['complete'])
        self.assertEqual('conversation_partial', self.service.conversation_block({'session_id':'main'}, {'main':preview}))
        found, offset = '', 0
        while offset is not None:
            result = self.service.conversation_read({'session_id':'main','revision':state['revision'],'offset':offset})
            self.assertLessEqual(sum(len(m['text']) for m in result['messages']), PAGE_CHARS)
            found += ''.join(m['text'] for m in result['messages']);offset=result['next_offset']
        self.assertTrue(result['complete'])
        self.assertEqual(found, ''.join(texts))
        self.assertIn('Old accepted promise', found);self.assertTrue(found.endswith('keep second open.'))
        self.assertTrue(self.service.conversation_states()['main']['complete'])
        # Only ranges/hashes persisted, not sensitive bodies or authority.
        self.assertNotIn('Old accepted promise', json.dumps(self.store.all('conversation_window')))
        self.assertEqual([], self.store.all('source_check'))
        self.assertEqual([], self.store.all('cursor'))

    def test_multiple_sessions_budget_and_new_message_race_invalidates_coverage(self):
        states = {str(i): self.state(str(i), ['z'*20000]) for i in range(20)}
        result = previews(self.store, states, self.now)
        self.assertLessEqual(sum(len(m['text']) for s in result.values() for m in s['messages']), PREVIEW_CHARS)
        self.assertTrue(all(not s['complete'] for s in result.values()))
        old = states['0'];first=page(self.store,old,{'revision':old['revision']},self.now)
        changed = self.state('0', ['z'*20000, 'User cancelled this scope'])
        refused = page(self.store,changed,{'revision':old['revision'],'offset':first['next_offset']},self.now)
        self.assertFalse(refused['available']);self.assertFalse(refused['complete'])
        self.assertFalse(previews(self.store, {'0':changed},self.now)['0']['complete'])

    def test_noncontiguous_chunk_cannot_fake_complete_and_partial_read_survives_resume(self):
        state=self.state('s',['A'*40000])
        last=page(self.store,state,{'revision':state['revision'],'offset':36000},self.now)
        self.assertEqual(last['next_offset'],0);self.assertFalse(last['complete'])  # Points at the first unread offset, not the tail.
        for off in (0,12000,24000):
            result=page(self.store,state,{'revision':state['revision'],'offset':off},self.now)
        self.assertTrue(result['complete'])
        # An edited old message with unchanged ID also invalidates the full revision.
        edited=self.state('s',['B'*40000])
        self.assertFalse(previews(self.store,{'s':edited},self.now)['s']['complete'])

    def test_inbox_soft_window_requires_both_cursors_and_next_intake(self):
        for n in range(501):
            self.now+=1;self.service.signal(str(n),'s','a'*8001)
        self.assertEqual(501,len(self.store.all('signal')))
        self.assertTrue(self.store.read('signal','0')['truncated'])
        self.store.write('cursor','memory-upkeep',self.now)
        self.service.signal('one','s','next');self.assertEqual(502,len(self.store.all('signal')))
        self.store.write('cursor','nightly-review',self.now)
        self.assertEqual(502,len(self.store.all('signal')))
        self.now+=1;self.service.signal('two','s','next')
        self.assertEqual(500,len(self.store.all('signal')))

    def test_audit_caps_assigned_workers_without_discarding_saved_pages(self):
        wave={'number':1,'done':False,'through':900,'pages':[{'slot':n,'events':1,'executions':0,'receipt':str(n),'reviewed':False} for n in (1,2,3)]}
        audit=Audit(SimpleNamespace(store=self.store, checkpoint=lambda:{"message_id":0}, clock=lambda:self.now))
        with patch('hermes_muse.delegation.settings',return_value={'max_concurrent_children':1}):
            result=audit.public(wave)
        self.assertEqual([1],[x['slot'] for x in result['assignments']]);self.assertEqual(3,len(wave['pages']))
        wave['pages'][0]['reviewed']=True
        with patch('hermes_muse.delegation.settings',return_value={'max_concurrent_children':1}):
            self.assertEqual([2],[x['slot'] for x in audit.public(wave)['assignments']])

    def test_effective_limit_configuration_environment_and_invalid_fallback(self):
        for cfg,env,want in [({},'1',1),({'max_concurrent_children':2},'1',2),({'max_concurrent_children':20},'1',3),({'max_concurrent_children':'bad'},'1',3),({'max_concurrent_children':0},'9',1)]:
            with patch('hermes_muse.delegation.settings',return_value=cfg),patch.dict(os.environ,{'DELEGATION_MAX_CONCURRENT_CHILDREN':env}):
                self.assertEqual(want,concurrency_limit())

    def test_internal_freshness_probe_does_not_mark_unreturned_text_as_served(self):
        state=self.state('s',['x'*2000])
        self.store.write('session','s',{'id':'s'})
        self.host.conversation=lambda sid,since: copy.deepcopy(state)
        check=self.service.conversation_states()['s']  # Internal delivery/finalization path.
        self.assertFalse(check['complete'])
        tail=self.service.conversation_read({'session_id':'s','revision':state['revision'],'offset':1000})
        self.assertEqual(tail['next_offset'],0)
        self.assertFalse(tail['complete'])  # The internal preview was never a returned tool receipt.
        self.assertTrue(self.service.conversation_read({'session_id':'s','revision':state['revision'],'offset':0})['complete'])
