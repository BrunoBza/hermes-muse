"""Historical binding uses exact native facts, preserving original attempts."""
import json
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_followup_recovery as recovery_tests
from hermes_muse.followup_recovery import rebind, apply, successful_successor
from hermes_muse.content_io import revision
from hermes_muse.views import canonical
from hermes_muse.followup import snapshot


class RebindTests(unittest.TestCase):
    setUp = recovery_tests.RecoveryTests.setUp
    message = recovery_tests.RecoveryTests.message
    manifest = recovery_tests.RecoveryTests.manifest
    receipt = recovery_tests.RecoveryTests.receipt

    def goal(self):
        self.service.signal('u', 's', 'Research this fixture')
        self.service.goal_create(dict(id='g', title='Fixture', description='Work', completion_criteria='Artifact', signal_id='u'))
        g, b = self.store.goal('g')
        g['followup'].update(result_state='verified', verification={'verified_at': self.now+20, 'summary':'new verification'})
        self.store.save_goal(g,b)
        self.now += 10
        self.message('Historical actual result.')
        return g

    def bind(self, **kw):
        g = self.store.goal('g')[0]
        data = dict(binding='reply', goal_id='g', message_id=1,
                    message_hash=revision(b'Historical actual result.'),
                    expected_revision=self.store.goal('g', with_fingerprint=True)[2], reason='Reviewed exact result for this goal')
        data.update(kw)
        return rebind(self.service.followups, data, self.now, session_id='s',turn_id='u')

    def test_reply_backfill_handoff_and_no_delivery_claim(self):
        self.goal(); r=self.bind(); g=self.store.goal('g')[0]
        self.assertNotIn('reply_id',g['followup'])
        self.service.followups.update(dict(kind='handoff',goal_id='g',expected_revision=g['followup']['revision'],reply_id=r['reply_id'],reason='Explicitly reviewed historical delivery'),session_id='s',turn_id='u')
        self.assertEqual(self.store.goal('g')[0]['followup']['delivery_state'],'unknown')
        self.assertEqual(snapshot(self.home,now=self.now+99999)['due_total'],0)
        with self.assertRaises(ValueError):
            apply(self.service.followups,dict(mode='rollback',repair_id=r['repair_id'],expected_revision=r['revision']),self.now,session_id='s')

    def test_reply_rollback_and_cas(self):
        before=self.goal(); r=self.bind()
        with patch('hermes_muse.runtime.session_info',return_value={'cron':False}), patch.dict('sys.modules', {'agent.delegation_context': SimpleNamespace(is_delegated_child_context=lambda: False)}):
            apply(self.service.followups,dict(mode='rollback',repair_id=r['repair_id'],expected_revision=r['revision']),self.now,session_id='s')
        self.assertEqual(self.store.goal('g')[0],before)
        self.assertIsNone(self.store.read('followup_reply',r['reply_id']))
        with self.assertRaises(ValueError):self.bind(expected_revision='stale')

    def test_reply_invalid_native_rows(self):
        self.goal()
        for field,value in [('session_id','other'),('role','tool'),('timestamp',self.now-20),('tool_calls','[{"id":"c"}]'),('display_kind','hidden')]:
            with self.subTest(field=field):
                with sqlite3.connect(self.home/'state.db') as db:
                    old=db.execute('SELECT '+field+' FROM messages WHERE id=1').fetchone()[0]
                    db.execute('UPDATE messages SET '+field+'=? WHERE id=1',(value,))
                with self.assertRaises(ValueError):self.bind()
                with sqlite3.connect(self.home/'state.db') as db:db.execute('UPDATE messages SET '+field+'=? WHERE id=1',(old,))
        with self.assertRaises(ValueError):self.bind(message_hash='0'*64)
        self.assertEqual(self.store.all('followup_repair'),[])

    def test_cancelled_and_new_input_not_bypassed(self):
        self.goal(); self.service.signal('new','s','Cancel the work')
        with self.assertRaisesRegex(ValueError,'newer user'):self.bind()
        g,b=self.store.goal('g');g['status']='cancelled';self.store.save_goal(g,b)
        with self.assertRaisesRegex(ValueError,'closed'):self.bind()

    def successor(self):
        self.goal()
        old=self.receipt('old','deleg_old');old.update(terminal=True,failed=True,native_status='interrupted',intent_id='intent')
        self.store.write('followup_receipt','old',old)
        g,b=self.store.goal('g');g['followup'].update(intent_id='intent',receipt_id='old',owner=old['owner'],execution_state='outcome_unknown');self.store.save_goal(g,b)
        self.receipt('next','deleg_next');self.manifest(['completed'],'deleg_next')
        with sqlite3.connect(self.home/'state.db') as db:
            db.executescript('ALTER TABLE messages ADD COLUMN tool_name TEXT; ALTER TABLE messages ADD COLUMN tool_call_id TEXT;')
        refs=[dict(kind='native_message',session_id='s',message_id=1,hash=revision(b'Historical actual result.'))]
        return old,refs

    def test_successor_keeps_original_and_enables_verification(self):
        old,refs=self.successor()
        r=self.bind(binding='successor',receipt_id='next',evidence_refs=refs)
        self.assertEqual(self.store.read('followup_receipt','old'),old)
        g=self.store.goal('g')[0];self.assertEqual(g['followup']['owner'],old['owner']);self.assertTrue(successful_successor(self.service,g))
        self.service.followups.update(dict(kind='verification',goal_id='g',expected_revision=g['followup']['revision'],result_state='verified',verified_at=self.now,summary='Accepted result',sources=['message:1'],evidence_refs=refs),session_id='s',turn_id='u')
        self.service.goal_update(dict(id='g',status='completed',outcome_evidence={'sources':['message:1'],'verified_at':self.now,'summary':'Accepted result'},evidence_refs=refs))
        self.assertEqual(self.store.goal('g')[0]['status'],'completed')
        self.assertEqual(self.store.read('followup_receipt','old'),old)

    def test_successor_requires_unchanged_successful_native_evidence(self):
        _,refs=self.successor()
        with self.assertRaises(ValueError):self.bind(binding='successor',receipt_id='next',evidence_refs=[])
        self.manifest(['interrupted'],'deleg_next')
        with self.assertRaises(ValueError):self.bind(binding='successor',receipt_id='next',evidence_refs=refs)
        self.manifest(['completed'],'deleg_next');self.bind(binding='successor',receipt_id='next',evidence_refs=refs)
        g,b=self.store.goal('g');g['followup']['scope_revision']+=1;self.assertFalse(successful_successor(self.service,g))
        self.manifest(['running'],'deleg_next');self.assertFalse(successful_successor(self.service,self.store.goal('g')[0]))

    def test_interrupted_write_preimage_can_rollback_without_clobbering(self):
        self.goal()
        for committed_file in (False, True):
            original = self.store.save_goal
            def interrupted(*args, **kwargs):
                if committed_file:
                    original(*args, **kwargs)
                raise RuntimeError('simulated crash')
            with patch.object(self.store, 'save_goal', side_effect=interrupted):
                with self.assertRaises(RuntimeError):self.bind()
            pending = [r for r in self.store.all('followup_repair') if r['state']=='pending'][-1]
            # File may commit before the DB transaction; related rows roll back.
            g = self.store.goal('g')[0]
            with patch('hermes_muse.runtime.session_info',return_value={'cron':False}), patch.dict('sys.modules', {'agent.delegation_context': SimpleNamespace(is_delegated_child_context=lambda: False)}):
                apply(self.service.followups,dict(mode='rollback',repair_id=pending['id'],expected_revision=revision(canonical(g))),self.now,session_id='s')
            self.assertIsNone(self.store.goal('g')[0]['followup'].get('bound_reply_id'))
            self.assertEqual(self.store.all('followup_reply'),[])

    def test_changed_original_attempt_or_foreign_successor_invalidates_binding(self):
        _, refs = self.successor()
        self.bind(binding='successor',receipt_id='next',evidence_refs=refs)
        g,b=self.store.goal('g');g['followup']['intent_id']='different'
        self.assertFalse(successful_successor(self.service,g))
        self.store.write('followup_intent','other-intent',{'goal_id':'other-goal'})
        receipt=self.store.read('followup_receipt','next');receipt['intent_id']='other-intent';self.store.write('followup_receipt','next',receipt)
        self.assertFalse(successful_successor(self.service,self.store.goal('g')[0]))

    def test_successor_rollback_restores_original_unknown_and_completed_scope_stays_closed(self):
        _,refs=self.successor()
        g,b=self.store.goal('g');g['status']='completed';self.store.save_goal(g,b)
        before=self.store.goal('g')[0]
        r=self.bind(binding='successor',receipt_id='next',evidence_refs=refs)
        self.assertEqual(self.store.goal('g')[0]['status'],'completed')
        with patch('hermes_muse.runtime.session_info',return_value={'cron':False}), patch.dict('sys.modules', {'agent.delegation_context': SimpleNamespace(is_delegated_child_context=lambda: False)}):
            apply(self.service.followups,dict(mode='rollback',repair_id=r['repair_id'],expected_revision=r['revision']),self.now,session_id='s')
        self.assertEqual(self.store.goal('g')[0],before)

    def test_bound_reply_cannot_deliver_negative_or_changed_native_text(self):
        self.goal()
        negative = 'Result is not ready. I have not delivered it.'
        with sqlite3.connect(self.home/'state.db') as db:
            db.execute('UPDATE messages SET content=? WHERE id=1',(negative,))
        r=self.bind(message_hash=revision(negative.encode()))
        g=self.store.goal('g')[0]
        args=dict(kind='handoff',goal_id='g',expected_revision=g['followup']['revision'],reply_id=r['reply_id'],reason='Claiming delivery')
        with self.assertRaises(ValueError):self.service.followups.update(args,session_id='s',turn_id='u')
        with sqlite3.connect(self.home/'state.db') as db:
            db.execute("UPDATE messages SET content='Changed text' WHERE id=1")
        with self.assertRaisesRegex(ValueError,'changed or is unavailable'):
            self.service.followups.update(args,session_id='s',turn_id='u')
        self.assertIsNone(self.store.goal('g')[0]['followup'].get('delivery_basis'))

    def second_goal(self):
        self.service.goal_create(dict(id='other',title='Other',description='Different work',completion_criteria='Other artifact',signal_id='u'))
        return self.store.goal('other')[0]

    def test_successor_cannot_be_consumed_by_two_goals(self):
        _,refs=self.successor();self.second_goal()
        self.bind(binding='successor',receipt_id='next',evidence_refs=refs)
        with self.assertRaisesRegex(ValueError,'already used by another goal'):
            self.bind(binding='successor',goal_id='other',expected_revision=self.store.goal('other',with_fingerprint=True)[2],receipt_id='next',evidence_refs=refs)
        # A legacy duplicate fact must invalidate BOTH consumers during revalidation.
        g=self.store.goal('g')[0];other,b=self.store.goal('other')
        other['followup']['successor']=dict(g['followup']['successor'])
        self.store.save_goal(other,b)
        self.assertFalse(successful_successor(self.service,g))
        self.assertFalse(successful_successor(self.service,other))

    def test_original_receipt_and_owner_reserve_successor_even_with_alias_receipts(self):
        _,refs=self.successor();self.second_goal()
        alias=self.receipt('alias','deleg_next')
        for fields in ({'receipt_id':'next'}, {'owner':alias['owner']}, {'receipt_id':'alias'},
                       {'successor':{'receipt_id':'alias','owner':alias['owner']}}):
            with self.subTest(fields=fields):
                other,b=self.store.goal('other');other['followup']={**other['followup'],'receipt_id':None,'owner':None,'successor':None,**fields}
                self.store.save_goal(other,b)
                with self.assertRaisesRegex(ValueError,'already used by another goal'):
                    self.bind(binding='successor',receipt_id='next',evidence_refs=refs)

    def delivered_successor(self):
        _,refs=self.successor();self.bind(binding='successor',receipt_id='next',evidence_refs=refs)
        g=self.store.goal('g')[0]
        self.service.followups.update(dict(kind='verification',goal_id='g',expected_revision=g['followup']['revision'],result_state='verified',verified_at=self.now,summary='Actual result',sources=['message:1'],evidence_refs=refs),session_id='s',turn_id='u')
        r=self.bind();g=self.store.goal('g')[0]
        self.service.followups.update(dict(kind='handoff',goal_id='g',expected_revision=g['followup']['revision'],reply_id=r['reply_id'],reason='Parent reviewed actual delivery'),session_id='s',turn_id='u')
        return refs

    def test_rebinding_preserves_unknown_delivery_and_blocks_duplicate_candidate(self):
        refs=self.delivered_successor();before=self.store.goal('g')[0]
        self.assertEqual(before['followup']['delivery_state'],'unknown')
        self.assertTrue(before['followup']['delivery_basis'])
        with self.assertRaisesRegex(ValueError,'existing delivery evidence'):
            self.bind(binding='successor',receipt_id='next',evidence_refs=refs)
        self.assertEqual(self.store.goal('g')[0],before)
        with self.assertRaisesRegex(ValueError,'unknown.*duplicate'):
            self.service.notification_add(dict(goal_id='g',final_result=True))
        self.assertEqual(self.store.all('notification'),[])

    def test_open_state_with_existing_basis_also_cannot_rebind(self):
        refs=self.delivered_successor();g,b=self.store.goal('g')
        g['followup']['delivery_state']='open';self.store.save_goal(g,b)
        with self.assertRaisesRegex(ValueError,'existing delivery evidence'):
            self.bind(binding='successor',receipt_id='next',evidence_refs=refs)
        self.assertEqual(self.store.goal('g')[0],g)

    def test_successor_receipt_and_message_must_each_strictly_follow_acceptance(self):
        _,refs=self.successor();at=self.store.goal('g')[0]['followup']['source_created_at']
        receipt=self.store.read('followup_receipt','next');receipt['observed_at']=at
        self.store.write('followup_receipt','next',receipt)
        with self.assertRaisesRegex(ValueError,'after acceptance'):
            self.bind(binding='successor',receipt_id='next',evidence_refs=refs)
        receipt['observed_at']=at+1;self.store.write('followup_receipt','next',receipt)
        with sqlite3.connect(self.home/'state.db') as db:
            db.execute('UPDATE messages SET timestamp=? WHERE id=1',(at,))
        with self.assertRaisesRegex(ValueError,'predates accepted goal'):
            self.bind(binding='successor',receipt_id='next',evidence_refs=refs)
        self.assertIsNone(self.store.goal('g')[0]['followup'].get('successor'))

    def test_concurrent_consumers_only_one_can_bind(self):
        from concurrent.futures import ThreadPoolExecutor
        _,refs=self.successor();self.second_goal()
        requests=[dict(binding='successor',goal_id=key,expected_revision=self.store.goal(key,with_fingerprint=True)[2],receipt_id='next',evidence_refs=refs,reason='Explicit same-scope parent judgment') for key in ('g','other')]
        def attempt(data):
            try:
                rebind(self.service.followups,data,self.now,session_id='s',turn_id='u')
                return True
            except ValueError as exc:
                self.assertIn('already used by another goal',str(exc))
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt,requests)),[False,True])
        self.assertEqual(sum(bool(g['followup'].get('successor')) for g in self.store.goals()),1)
