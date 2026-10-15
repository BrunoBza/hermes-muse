import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from test_companion import prepare, Host
from hermes_muse.service import Companion
from hermes_muse.followup import snapshot
from hermes_muse.followup_recovery import native_terminal, diagnose, apply, automatic
from hermes_muse.store import digest
from hermes_muse.views import canonical
from hermes_muse.content_io import revision


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.store = prepare(self.home)
        self.now = 1800000000
        self.service = Companion(self.store, Host(), lambda: self.now)
        with sqlite3.connect(self.home / 'state.db') as db:
            db.executescript("CREATE TABLE sessions(id TEXT,chat_type TEXT); INSERT INTO sessions VALUES('s','private'); CREATE TABLE messages(id INTEGER,session_id TEXT,role TEXT,content TEXT,timestamp REAL,tool_calls TEXT,display_kind TEXT); CREATE TABLE async_delegations(delegation_id TEXT,origin_session_id TEXT,state TEXT,result_json TEXT);")

    def receipt(self, key='r', owner='deleg_a'):
        row = dict(id=key, owner={'kind': 'native_delegation', 'id': owner}, session_id='s', turn_id='u', tool_call_id='c', intent_id=None, native_status='dispatched', terminal=False, failed=False, observed_at=self.now)
        self.store.write('followup_receipt', key, row)
        return row

    def manifest(self, states, owner='deleg_a'):
        p = self.home / 'cache/delegation/live' / owner
        p.mkdir(parents=True, exist_ok=True)
        (p / 'manifest.json').write_text(json.dumps({'delegation_id': owner, 'completed': 'now', 'task_count': len(states), 'tasks': [{'index': i, 'status': s} for i,s in enumerate(states)]}))

    def mutate(self, kind, row, **kw):
        return apply(self.service.followups, dict(mode='apply', object_kind=kind, id=row['id'], expected_revision=revision(canonical(row)), **kw), self.now)

    def message(self, text, mid=1):
        with sqlite3.connect(self.home / 'state.db') as db:
            db.execute("INSERT INTO messages VALUES(?,'s','assistant',?,?,NULL,NULL)", (mid, text, self.now))

    def test_manifest_completed_interrupted_failed_missing_and_duplicates(self):
        for status in ['completed', 'interrupted', 'failed']:
            owner = 'deleg_' + status
            self.manifest([status], owner)
            for suffix in ['a','b']:
                row = self.receipt(status + suffix, owner)
                result = self.mutate('followup_receipt', row)
                self.assertTrue(result['changed'])
                self.assertEqual(self.store.read('followup_receipt', row['id'])['native_status'], status)
                self.assertEqual(self.store.read('followup_receipt', row['id'])['failed'], status != 'completed')
        missing = self.receipt('missing', 'deleg_missing')
        self.assertIsNone(native_terminal(self.home, missing))
        self.assertEqual(snapshot(self.home)['orphan_total'], 1)
        self.assertEqual(len(self.store.all('followup_receipt')), 7)  # retained, not deleted

    def test_durable_precedence_cross_session_running_and_unknown(self):
        row = self.receipt()
        self.manifest(['completed'])
        with sqlite3.connect(self.home / 'state.db') as db:
            db.execute('INSERT INTO async_delegations VALUES(?,?,?,?)', ('deleg_a', 'other', 'completed', '{}'))
        self.assertIsNone(native_terminal(self.home, row))
        with sqlite3.connect(self.home / 'state.db') as db:
            db.execute("UPDATE async_delegations SET origin_session_id='s', state='running'")
        self.assertIsNone(native_terminal(self.home, row))
        with sqlite3.connect(self.home / 'state.db') as db:
            db.execute("UPDATE async_delegations SET state='completed', result_json=?", (json.dumps({'results':[{'status':'interrupted'}]}),))
        self.assertIsNone(native_terminal(self.home, row))  # contradictory completed manifest
        self.manifest(['interrupted'])
        self.assertEqual(native_terminal(self.home, row)['native_status'], 'interrupted')

    def test_manifest_symlink_and_partial_rejected(self):
        row = self.receipt(); self.manifest(['completed','running'])
        self.assertIsNone(native_terminal(self.home, row))
        path = self.home / 'cache/delegation/live/deleg_a/manifest.json'
        path.rename(path.with_suffix('.other'))
        path.symlink_to(path.with_suffix('.other'))
        self.assertIsNone(native_terminal(self.home, row))

    def test_dry_read_backup_rollback_conflict_and_scope(self):
        row=self.receipt(); self.manifest(['completed'])
        before=(self.home/'muse/state.db').read_bytes()
        plan=diagnose(self.home,{},self.now)
        self.assertEqual((self.home/'muse/state.db').read_bytes(),before)
        self.assertTrue(plan['items'][0]['change'])
        result=self.mutate('followup_receipt',row)
        backup=self.store.read('followup_repair',result['repair_id'])
        self.assertEqual(backup['before'],row)
        restore=apply(self.service.followups,{'mode':'rollback','repair_id':result['repair_id'],'expected_revision':result['revision']},self.now)
        self.assertTrue(restore['changed']);self.assertEqual(self.store.read('followup_receipt','r'),row)
        with self.assertRaisesRegex(ValueError,'scope'):
            diagnose(self.home,{'scope_token':'foreign'},self.now)
        with self.assertRaisesRegex(ValueError,'Reread'):
            self.mutate('followup_receipt',{**row,'terminal':True})

    def goal_reply(self, text='Verified fixture artifact', response=None):
        self.service.signal('u','s','Research this fixture')
        self.service.goal_create({'id':'g','title':'Fixture','description':'Fixture','completion_criteria':'Artifact','signal_id':'u'})
        goal,body=self.store.goal('g');goal['followup'].update(execution_state='finished',result_state='verified',verification={'verified_at':self.now-100,'summary':text})
        self.store.save_goal(goal,body)
        self.message(response or text)
        self.store.write('followup_reply','reply',{'id':'reply','session_id':'s','turn_id':'u','observed_at':self.now+60,'assistant_hash':digest(response or text),'message_id':None})
        return goal

    def reviewed_goal(self):
        goal=self.goal_reply()
        from hermes_muse.followup_recovery import exact_reply
        reply=self.store.read('followup_reply','reply')
        resolved,history=exact_reply(self.home,reply)
        self.service.host.conversation=lambda *args:history
        self.service.followups.update({'kind':'handoff','goal_id':'g','expected_revision':goal['followup']['revision'],
                                      'reply_id':'reply','reason':'Parent reviewed the original final result as handed off'})
        goal,body=self.store.goal('g')
        goal['followup'].update(delivery_basis=None,reply_id=None,delivery_state='open',blocker_class=None,next_check_at=self.now)
        self.store.save_goal(goal,body)  # simulate missing derived projection, preserve review receipt
        return goal

    def test_actual_reply_missing_hook_id_and_old_timestamp_converges_not_confirmed(self):
        goal=self.reviewed_goal()
        result=self.mutate('goal',goal);self.assertTrue(result['changed'])
        fu=self.store.goal('g')[0]['followup'];self.assertEqual(fu['delivery_state'],'unknown')
        self.assertEqual(fu['delivery_basis']['status'],'recorded_unconfirmed')
        self.assertEqual(snapshot(self.home,now=self.now)['due_total'],0)
        self.assertFalse(self.mutate('goal',self.store.goal('g')[0])['changed'])
        self.assertEqual(len(self.store.all('notification')),0)

    def test_unrelated_ambiguous_and_cancelled_reply_stay_unproven(self):
        goal=self.goal_reply(response='Different result')
        self.assertFalse(self.mutate('goal',goal)['changed'])
        self.message('Different result',2)
        self.assertFalse(self.mutate('goal',goal)['changed'])
        goal,body=self.store.goal('g');goal['status']='cancelled';self.store.save_goal(goal,body)
        self.assertFalse(self.mutate('goal',goal)['changed'])

    def test_ordinary_answer_settles_but_promises_failed_and_clarification_do_not(self):
        self.service.signal('u','s','What is the status?');self.message('All installed services are running.')
        self.service.followups.finish_turn('s','u',response='All installed services are running.')
        automatic(self.service.followups,'s',self.now)
        turn=self.store.all('followup_turn')[0];self.assertEqual(turn['disposition'],'no_commitment')
        self.assertEqual(self.store.goals(),[])
        for key, text, flags in [('v','I will check later.',{}),('w','All services are running.',{'failed':True})]:
            self.service.signal(key,'s','What is the status?');self.message(text,len(key)+ord(key))
            self.service.followups.finish_turn('s',key,response=text,**flags)
            automatic(self.service.followups,'s',self.now)
            self.assertEqual(self.store.read('followup_turn',digest('s:'+key))['disposition'],'pending')

    def test_pagination_over_existing_scale_and_concurrent_new_ids(self):
        for i in range(180): self.receipt(f'r{i:03}',f'deleg_{i}')
        cursor='';seen=[]
        while True:
            page=diagnose(self.home,{'cursor':cursor},self.now)
            self.assertLess(len(json.dumps(page).encode()),262144)
            seen += [x['id'] for x in page['items']]
            cursor=page['next_cursor']
            if not cursor:break
        self.assertEqual(len(set(seen)),180)

    def test_unknown_terminal_is_still_due_and_cancelled_late_receipt_not_reopened(self):
        r=self.receipt();r.update(terminal=True,native_status='unknown');self.store.write('followup_receipt','r',r)
        self.assertEqual(snapshot(self.home)['orphan_total'],1)
        self.manifest(['completed']);self.assertTrue(self.mutate('followup_receipt',r)['changed'])
        goal=self.goal_reply();goal,body=self.store.goal('g')
        goal['followup'].update(execution_state='waiting_external',result_state='unverified',intent_id='i',receipt_id='r')
        r=self.store.read('followup_receipt','r');r.update(intent_id='i',scope_revision=goal['followup']['scope_revision']);self.store.write('followup_receipt','r',r)
        self.store.save_goal(goal,body);self.assertTrue(self.mutate('goal',goal)['changed'])
        self.assertEqual(self.store.goal('g')[0]['followup']['result_state'],'unverified')
        goal,body=self.store.goal('g');goal['status']='cancelled';goal['followup']['execution_state']='waiting_external';self.store.save_goal(goal,body)
        self.assertFalse(self.mutate('goal',goal)['changed'])

    def test_goal_rollback_is_cas_and_preserves_concurrent_body(self):
        goal=self.reviewed_goal();result=self.mutate('goal',goal)
        self.store.write_text('workspace/goals/g/files/other.md','Unrelated file retained')
        current,body=self.store.goal('g');self.store.save_goal(current,body+'User appended note')
        apply(self.service.followups,{'mode':'rollback','repair_id':result['repair_id'],'expected_revision':result['revision']},self.now)
        self.assertIn('User appended note',self.store.goal('g')[1])
        self.assertEqual(self.store.goal('g')[0]['followup']['delivery_state'],'open')

    def test_existing_maintenance_rotates_past_unknown_without_new_jobs(self):
        for i in range(65):
            row=self.receipt(f'r{i:03}',f'deleg_{i}')
            if i >= 30: self.manifest(['completed'],row['owner']['id'])
        for _ in range(4): automatic(self.service.followups,None,self.now)
        self.assertEqual(snapshot(self.home)['orphan_total'],30)
        self.assertEqual(self.store.goals(),[])

    def test_negative_mention_and_unreviewed_positive_never_prove_handoff(self):
        goal=self.goal_reply(text='Verified negative artifact', response='Verified negative artifact is not ready. I have not delivered the result; it remains blocked.')
        for answer in ['Verified negative artifact is not ready. I have not delivered the result; it remains blocked.',
                       'Verified negative artifact 尚未准备好，没有交付。',
                       'Only mentioning files/result.md; this is an earlier phase.', 'Verified negative artifact']:
            with sqlite3.connect(self.home/'state.db') as db:db.execute('UPDATE messages SET content=?',(answer,))
            row=self.store.read('followup_reply','reply');row['assistant_hash']=digest(answer);self.store.write('followup_reply','reply',row)
            self.assertFalse(self.mutate('goal',goal)['changed'])
            self.assertEqual(snapshot(self.home,now=self.now)['due_total'],1)

    def test_corrupt_durable_never_falls_back_even_for_failed_or_running(self):
        row=self.receipt();self.manifest(['completed'])
        for state in ['running','interrupted','failed','completed']:
            with sqlite3.connect(self.home/'state.db') as db:
                db.execute('DELETE FROM async_delegations')
                db.execute('INSERT INTO async_delegations VALUES(?,?,?,?)',('deleg_a','s',state,'{broken'))
            self.assertIsNone(native_terminal(self.home,row),state)
        with sqlite3.connect(self.home/'state.db') as db:db.execute('DROP TABLE async_delegations')
        self.assertIsNone(native_terminal(self.home,row))  # unsupported schema is not missing row

    def test_review_receipt_invalidated_by_result_or_reply_changes(self):
        goal=self.reviewed_goal()
        goal['followup']['verification']['summary']='New result version'
        _,body=self.store.goal('g');self.store.save_goal(goal,body)
        self.assertFalse(self.mutate('goal',goal)['changed'])
        goal['followup']['verification']['summary']='Verified fixture artifact';self.store.save_goal(goal,body)
        reply=self.store.read('followup_reply','reply');reply['assistant_hash']=digest('Not delivered');self.store.write('followup_reply','reply',reply)
        self.assertFalse(self.mutate('goal',goal)['changed'])

    def new_turn(self, text, answer, key='new'):
        self.now+=1
        self.service.signal(key,'s',text);self.message(answer,self.now)
        self.service.followups.finish_turn('s',key,response=answer)
        return self.store.read('followup_turn',digest('s:'+key))

    def test_answered_inquiry_with_optional_question_does_not_hold_old_goal(self):
        self.reviewed_goal()
        self.new_turn('How is the unrelated service?', 'It is healthy. Would you like more detail?')
        automatic(self.service.followups,'s',self.now)
        self.assertEqual(self.store.read('followup_turn',digest('s:new'))['disposition'],'no_commitment')
        self.assertEqual(self.store.goal('g')[0]['followup']['delivery_basis']['kind'],'reply')

    def test_related_cancel_and_unanswered_inquiry_still_block(self):
        goal=self.reviewed_goal()
        for text in ['What is the status? Cancel g.', 'How is g? Pause it now.']:
            self.new_turn(text,'Current status recorded.')
            automatic(self.service.followups,'s',self.now)
            plan=diagnose(self.home,{},self.now);item=next(x for x in plan['items'] if x['id']=='g')
            self.assertFalse(item['change']);self.assertIsNotNone(item['blocked_by'])
            with self.assertRaisesRegex(ValueError,'Review newer'):self.mutate('goal',goal)
        self.now+=1;self.service.signal('active','s','What is the status?')
        with self.assertRaisesRegex(ValueError,'Review newer'):self.mutate('goal',goal)

    def test_explicit_unrelated_review_is_per_goal_and_version_not_blanket(self):
        goal=self.reviewed_goal()
        row=self.new_turn('Investigate another project.', 'That separate project has an ongoing investigation.')
        self.assertIsNotNone(next(x for x in diagnose(self.home,{},self.now)['items'] if x['id']=='g')['blocked_by'])
        self.service.followups.review({'kind':'review','candidate_id':row['id'],'expected_revision':row['revision'],
                                      'disposition':'unrelated','goal_ids':['g'],'reason':'Read original turn and final reply; it concerns a separate project'})
        row=self.store.read('followup_turn',row['id']);self.assertEqual(row['disposition'],'pending')
        self.assertTrue(self.mutate('goal',goal)['changed'])
        goal,body=self.store.goal('g');goal['followup']['scope_revision']+=1;self.store.save_goal(goal,body)
        with self.store.transaction() as db:
            with self.assertRaisesRegex(ValueError,'Review newer'):
                self.service.followups._gate(db,goal,goal['followup'],allow_terminal=True)
        self.assertFalse(self.mutate('goal',goal)['changed'])  # stale handoff review is also unusable

    def test_negative_handoff_action_is_vetoed_even_when_summary_matches(self):
        goal=self.goal_reply(response='Verified fixture artifact is not ready. I have not delivered the result.')
        from hermes_muse.followup_recovery import exact_reply
        reply=self.store.read('followup_reply','reply');resolved,history=exact_reply(self.home,reply)
        self.service.host.conversation=lambda *args:history
        with self.assertRaisesRegex(ValueError,'does not contain'):
            self.service.followups.update({'kind':'handoff','goal_id':'g','expected_revision':goal['followup']['revision'],
                                          'reply_id':'reply','reason':'Incorrect handoff assertion'})
        self.assertIsNone(self.store.read('followup_handoff','g'))
        from hermes_muse.delivery import handoff_review
        self.store.write('followup_handoff','g',handoff_review(goal,resolved,self.now))
        self.assertFalse(self.mutate('goal',goal)['changed'])

    def test_unrelated_review_does_not_hide_older_related_input_or_changed_reply(self):
        goal=self.reviewed_goal()
        related=self.new_turn('Cancel g.','The cancellation is awaiting processing.',key='related')
        separate=self.new_turn('Investigate a separate project.','Separate work is ongoing.',key='separate')
        self.service.followups.review({'kind':'review','candidate_id':separate['id'],'expected_revision':separate['revision'],
                                      'disposition':'unrelated','goal_ids':['g'],'reason':'Separate scope reviewed'})
        item=next(x for x in diagnose(self.home,{},self.now)['items'] if x['id']=='g')
        self.assertEqual(item['blocked_by']['candidate_id'],related['id'])
        with self.assertRaisesRegex(ValueError,'Review newer'):self.mutate('goal',goal)
        # A settled unrelated review cannot survive a different final reply.
        self.service.followups.finish_turn('s','separate',response='Now cancel g too.')
        item=next(x for x in diagnose(self.home,{},self.now)['items'] if x['id']=='g')
        self.assertEqual(item['blocked_by']['candidate_id'],separate['id'])
