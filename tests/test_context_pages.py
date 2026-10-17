import json
import tempfile
import unittest
from pathlib import Path
from test_companion import prepare, Host
from hermes_muse.service import Companion
from hermes_muse.context_pages import context
from hermes_muse.content_io import DomainError
from hermes_muse.conversation import descriptor, page, REVIEW_CHARS
from hermes_muse.store import digest
from hermes_muse.views import Views


class ContextPagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = prepare(Path(self.tmp.name))
        self.now = 1800000000
        self.service = Companion(self.store, Host(), lambda: self.now)

    def test_goal_list_projects_state_orders_open_first_and_filters_status(self):
        self.service.signal('s', 'parent', 'Plan several things')
        for key in ('quiet', 'wait', 'stuck', 'old'):
            self.service.goal_create({'id': key, 'title': key.title(), 'description': 'd',
                                      'completion_criteria': 'c', 'signal_id': 's'})
        self.service.goal_update({'id': 'wait', 'waiting_user': True, 'progress': 'x' * 600})
        self.service.goal_update({'id': 'stuck', 'blocked': 'Needs a key'})
        self.service.goal_update({'id': 'old', 'status': 'done', 'note': 'Finished'})
        views = Views(self.store.home)
        order = lambda **q: [r['id'] for r in views.read({'kind': 'goal', **q})['items']]
        self.assertEqual(order(), ['wait', 'stuck', 'quiet', 'old'])
        self.assertEqual(order(status='open'), ['wait', 'stuck', 'quiet'])
        self.assertEqual(order(status='closed'), ['old'])
        page = views.read({'kind': 'goal', 'status': 'open', 'limit': 2})
        self.assertEqual(page['total'], 3)
        rest = views.read({'kind': 'goal', 'status': 'open', 'limit': 2, 'cursor': page['next_cursor']})
        self.assertEqual([r['id'] for r in rest['items']], ['quiet'])
        wait = page['items'][0]
        self.assertTrue(wait['waiting_user'])
        self.assertEqual(len(wait['latest_progress']['text']), 512)
        self.assertTrue(wait['summary_truncated'])
        self.assertEqual(page['items'][1]['blocked'], 'Needs a key')
        for bad in ({'kind': 'goal', 'status': 'bogus'}, {'kind': 'feed', 'status': 'open'}):
            with self.assertRaises(DomainError):
                views.read(bad)

    def test_idea_list_reports_last_nightly_review(self):
        views = Views(self.store.home)
        self.assertIsNone(views.read({'kind': 'idea'})['last_review_at'])
        with self.store.transaction() as db:
            self.store.put(db, 'run', 'r1', {'id': 'r1', 'job': 'nightly-review', 'started': 123.0})
        self.assertEqual(views.read({'kind': 'idea'})['last_review_at'], 123.0)

    def test_large_signal_window_ties_append_edit_and_checkpoint(self):
        with self.store.transaction() as db:
            for i in range(220):
                self.store.put(db, 'signal', str(i), {'id': str(i), 'session_id': 's', 'created': self.now-10+i//110, 'text': '证据' * 16000})
        first = context(self.service, {'section':'signals','job':'memory-upkeep','limit':17})
        token, through = first['window'], first['through']
        checkpoint = {'job':'memory-upkeep','window':token,'through':through,'up_to':self.now-10,'summary':'Substantive review'}
        with self.assertRaises(DomainError):self.service.review_complete(checkpoint, require_window=True)
        ids=[];p=first
        while True:
            ids.extend(r['id'] for r in p['items'])
            if not p['next_cursor']:break
            p=context(self.service,{'section':'signals','job':'memory-upkeep','window':token,'cursor':p['next_cursor'],'limit':17})
        self.assertEqual(len(set(ids)),220)
        self.now+=1
        self.store.write('signal','new',{'id':'new','session_id':'s','created':self.now,'text':'Later signal'})
        for key in ids:
            off=0
            while off is not None:
                p=context(self.service,{'section':'signals','job':'memory-upkeep','window':token,'id':key,'offset':off})
                self.assertLess(len(json.dumps(p).encode()),256*1024)
                off=p['next_offset']
        r=self.service.review_complete(checkpoint,require_window=True)
        self.assertEqual(r['remaining'],110)
        r=self.service.review_complete({**checkpoint,'up_to':through},require_window=True)
        self.assertTrue(r['complete'])
        self.assertEqual(context(self.service,{'section':'signals','job':'memory-upkeep'})['total'],1)
        row=self.store.read('signal','0');row['text']='Changed';self.store.write('signal','0',row)
        with self.assertRaises(DomainError):context(self.service,{'section':'signals','job':'memory-upkeep','window':token})

    def test_history_append_keeps_prefix_edit_does_not_and_dense_messages_fit(self):
        def state(texts):
            ms=[{'id':i,'text':t,'role':'user','at':self.now} for i,t in enumerate(texts)]
            return {'available':True,'session_id':'s','messages':ms,'revision':digest(json.dumps(ms)),'since':self.now-86400}
        s=state(['x'*20000,'y'*20000]);d=descriptor(self.store,s,self.now)
        p=page(self.store,s,{'revision':d['revision'],'offset':0},self.now)
        grown=state(['x'*20000,'y'*20000,'new correction'])
        p=page(self.store,grown,{'revision':s['revision'],'offset':12000},self.now)
        self.assertFalse(p['available']);self.assertEqual(p['next_offset'],40014-REVIEW_CHARS)  # Retained prefix plus review window.
        offset=p['next_offset']
        while offset is not None:
            p=page(self.store,grown,{'revision':grown['revision'],'offset':offset},self.now);offset=p['next_offset']
        self.assertTrue(p['complete'])
        changed=state(['EDIT'+'x'*20000,'y'*20000,'new correction'])
        self.assertEqual(descriptor(self.store,changed,self.now)['next_offset'],40018-REVIEW_CHARS)
        dense=state(['a']*15000)
        p=page(self.store,dense,{'revision':dense['revision'],'offset':0},self.now)
        self.assertLess(len(json.dumps(p).encode()),256*1024);self.assertLess(p['next_offset'],12000)

    def test_truncated_signal_requires_original_and_detects_edits(self):
        original = {'id':1,'role':'user','at':self.now,'text':'x'*45000}
        self.service.host.conversation=lambda sid,since: {'available':True,'messages':[original]}
        self.service.signal('long','s',original['text'])
        self.assertTrue(self.store.read('signal','long')['truncated'])
        first=context(self.service,{'section':'signals','job':'memory-upkeep'})
        data={'section':'signals','job':'memory-upkeep','window':first['window'],'id':'long','length':6000}
        part=context(self.service,data)
        cp={'job':'memory-upkeep','window':first['window'],'through':first['through'],'up_to':first['through'],'summary':'Reviewed original'}
        with self.assertRaises(DomainError):self.service.review_complete(cp,require_window=True)
        while part['next_offset'] is not None:
            part=context(self.service,{**data,'offset':part['next_offset']})
        original['text']+='edited suffix'
        with self.assertRaises(DomainError):self.service.review_complete(cp,require_window=True)
        self.service.host.conversation=lambda sid,since: {'available':True,'messages':[]}
        with self.assertRaises(DomainError):context(self.service,data)
        self.assertEqual(self.store.read('cursor','memory-upkeep',0),0)

    def test_large_metadata_and_discovery_are_consumable(self):
        self.store.write('run','huge',{'id':'huge','status':'partial','summary':'x'*500000,'stages':{}})
        view=Views(self.store.home);p=view.read({'kind':'run','id':'huge'})
        self.assertFalse(p['metadata_complete']);ref=p['metadata_ref']['data'];off=0;body=''
        while off is not None:
            p=view.read({**ref,'offset':off});body+=p['body'];off=p['next_offset']
        self.assertEqual(len(json.loads(body)['summary']),500000)
        self.assertLess(len(json.dumps(context(self.service,{})).encode()),12000)
        self.assertIn('operation_review', context(self.service,{}))
        self.store.save_goal({'id':'large-goal','title':'Goal','status':'active','progress':['x'*50000],
                              'revision':1,'owner':{'kind':'native_delegation','id':'native-owner'}}, '# Goal')
        projected=view.read({'kind':'goal','id':'large-goal'})
        self.assertFalse(projected['metadata_complete'])
        meta='';off=0
        while off is not None:
            part=view.read({**projected['metadata_ref']['data'],'offset':off});meta+=part['body'];off=part['next_offset']
        self.assertEqual(json.loads(meta)['owner']['id'],'native-owner')
