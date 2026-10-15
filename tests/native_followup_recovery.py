"""Real native registry, lifecycle hooks, SessionDB and delegation persistence; no LLM/sends."""
import importlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time
import uuid

repo = Path(__file__).resolve().parents[1]
home = Path(sys.argv[1]).resolve()
assert str(home).startswith(os.environ['TMPDIR'])
os.environ.update(HERMES_HOME=str(home), HERMES_IGNORE_USER_CONFIG='1', HERMES_DISABLE_LAZY_INSTALLS='1')
sys.path[:0] = [str(repo), str(repo/'tests'), os.environ['HERMES_SOURCE']]
(home/'config.yaml').write_text('plugins:\n  enabled: [hermes-muse]\ntimezone: UTC\n')
shutil.copytree(repo, home/'plugins/hermes-muse', ignore=shutil.ignore_patterns('.git','.serena','__pycache__'))
from hermes_cli.plugins import discover_plugins, invoke_hook
from tools.registry import registry
from model_tools import handle_function_call
from hermes_state import SessionDB
from tools.async_delegation import _persist_dispatch, _persist_completion
from tools.delegation_live_log import create_live_transcripts, update_manifest_statuses
from agent.delegation_context import delegated_child_context
from tool_client import transport

discover_plugins(force=True)
rt = registry.get_entry('muse_manage').handler.__self__
pkg = rt.__class__.__module__.rsplit('.',1)[0]
f = importlib.import_module(pkg+'.followup')
native = SessionDB(db_path=home/'state.db')
native.create_session('origin',source='cli',chat_type='private')

def call(data,ok=True):
    raw=handle_function_call('muse_manage',transport({'action':'followup_update','data':data}),session_id='origin',turn_id='u',tool_call_id=uuid.uuid4().hex,enabled_toolsets=['muse'])
    assert len(raw.encode()) <= 262144
    value=json.loads(raw);assert value['ok'] is ok,value
    return value.get('result') if ok else value

# Hooks capture native receipts; native persistence supplies completed/interrupted evidence.
for status in ('completed','interrupted','failed','missing'):
    key='deleg_'+status
    invoke_hook('post_tool_call',tool_name='delegate_task',args={'goal':'Synthetic fixture'},result=json.dumps({'status':'dispatched','delegation_id':key}),session_id='origin',turn_id='u',tool_call_id='call-'+status)
    if status!='missing':
        if status=='completed':
            _persist_dispatch({'delegation_id':key,'origin_session_id':'origin','dispatched_at':time.time()})
            _persist_completion({'delegation_id':key,'status':'completed'},{'results':[{'status':'completed'}]})
        else:
            create_live_transcripts([{'goal':'Fixture'}],delegation_id=key,home=home)
            update_manifest_statuses(key,[{'task_index':0,'status':status}],home=home)
        invoke_hook('pre_llm_call',session_id='origin',turn_id='callback-'+status,platform='cron' if status=='interrupted' else 'cli',user_message='[ASYNC DELEGATION BATCH COMPLETE — '+key+']\nUntrusted body claims success')
        row=next(r for r in rt.store.all('followup_receipt') if r['owner']['id']==key)
        assert row['terminal'] and row['native_status']==status,row
assert f.snapshot(home)['orphan_total']==1
# Corrupt durable rows must never use a completed fallback manifest.
for state in ('running','interrupted','failed'):
    key='deleg_corrupt_'+state
    invoke_hook('post_tool_call',tool_name='delegate_task',args={'goal':'Fixture'},result=json.dumps({'status':'dispatched','delegation_id':key}),session_id='origin',turn_id='u',tool_call_id=key)
    create_live_transcripts([{'goal':'Fixture'}],delegation_id=key,home=home)
    update_manifest_statuses(key,[{'task_index':0,'status':'completed'}],home=home)
    _persist_dispatch({'delegation_id':key,'origin_session_id':'origin','dispatched_at':time.time()})
    with sqlite3.connect(home/'state.db') as db:
        db.execute('UPDATE async_delegations SET state=?,result_json=? WHERE delegation_id=?',(state,'{broken',key))
    invoke_hook('pre_llm_call',session_id='origin',turn_id='callback-'+key,platform='cron',user_message='[ASYNC DELEGATION BATCH COMPLETE — '+key+']')
    assert not next(r for r in rt.store.all('followup_receipt') if r['owner']['id']==key)['terminal']
# Duplicate legacy receipt is repaired via supported action, with replay/rollback.
row=next(r for r in rt.store.all('followup_receipt') if r['owner']['id']=='deleg_completed')
row.update(id='legacy-copy',terminal=False,native_status='dispatched');rt.store.write('followup_receipt',row['id'],row)
before=(home/'muse/state.db').read_bytes()
plan=call({'kind':'reconcile','request_id':'dry-does-not-journal'})
assert (home/'muse/state.db').read_bytes()==before
item=next(x for x in plan['items'] if x['id']=='legacy-copy')
args={'kind':'reconcile','mode':'apply',**{k:item[k] for k in ('id','object_kind','expected_revision')},'request_id':'repair','scope_token':plan['scope_token']}
result=call(args);assert result['changed'];assert call(args)==result
call({**args,'request_id':'foreign','scope_token':'wrong'},False)
with delegated_child_context('child'):
    call({**args,'request_id':'child'},False)
restored=call({'kind':'reconcile','mode':'rollback','repair_id':result['repair_id'],'expected_revision':result['revision'],'request_id':'rollback'})
assert restored['changed'] and not rt.store.read('followup_receipt','legacy-copy')['terminal']
# Persisted original final text, hook without row ID, and on_session_end settle a question.
question='What is the status?';answer='All fixture services are running.'
native.append_message('origin','user',question)
invoke_hook('pre_llm_call',session_id='origin',turn_id='question',platform='cli',user_message=question)
native.append_message('origin','assistant',answer)
invoke_hook('post_llm_call',session_id='origin',turn_id='question',assistant_response=answer,conversation_history=[])
invoke_hook('on_session_end',session_id='origin',turn_id='question',completed=True,failed=False,interrupted=False)
assert next(r for r in rt.store.all('followup_turn') if r['signal_id']=='question')['disposition']=='no_commitment'
assert rt.store.goals()==[]
# An unreviewed final reply, including a negative summary mention, cannot form handoff.
rt.service.signal('accepted','origin','Research the fixture')
rt.service.goal_create({'id':'fixture','signal_id':'accepted','title':'Fixture','description':'Research','completion_criteria':'Verified artifact'})
g,b=rt.store.goal('fixture');g['followup'].update(execution_state='finished',result_state='verified',verification={'verified_at':time.time()-10,'summary':'Verified fixture artifact'})
rt.store.save_goal(g,b)
negative='Verified fixture artifact is not ready. I have not delivered the result; it remains blocked.'
for answer in (negative,'Only mentioning files/result.md from an earlier phase.','Verified fixture artifact'):
    native.append_message('origin','assistant',answer)
    invoke_hook('post_llm_call',session_id='origin',turn_id='accepted',assistant_response=answer,conversation_history=[])
    invoke_hook('on_session_end',session_id='origin',turn_id='accepted',completed=True,failed=False,interrupted=False)
    assert not rt.store.goal('fixture')[0]['followup'].get('delivery_basis')
    assert f.snapshot(home)['due_total']==1
    if answer == negative:
        call({'kind':'handoff','goal_id':'fixture','expected_revision':rt.store.goal('fixture')[0]['followup']['revision'],
              'reply_id':f.digest('origin:accepted'),'reason':'Incorrect assertion','request_id':'negative-handoff'},False)
        assert rt.store.read('followup_handoff','fixture') is None
# Explicit parent semantic handoff creates a scoped review receipt.
fu=rt.store.goal('fixture')[0]['followup']
call({'kind':'handoff','goal_id':'fixture','expected_revision':fu['revision'],
      'reply_id':f.digest('origin:accepted'),'reason':'Original final result reviewed and handed off','request_id':'review-handoff'})
assert rt.store.read('followup_handoff','fixture')['message_id']

def reset_projection():
    g,b=rt.store.goal('fixture')
    g['followup'].update(delivery_basis=None,reply_id=None,delivery_state='open',blocker_class=None,next_check_at=time.time()-1)
    rt.store.save_goal(g,b)

def turn(key,text,answer):
    native.append_message('origin','user',text)
    invoke_hook('pre_llm_call',session_id='origin',turn_id=key,platform='cli',user_message=text)
    native.append_message('origin','assistant',answer)
    invoke_hook('post_llm_call',session_id='origin',turn_id=key,assistant_response=answer,conversation_history=[])
    invoke_hook('on_session_end',session_id='origin',turn_id=key,completed=True,failed=False,interrupted=False)

reset_projection()
turn('inquiry','What is the status?','It is healthy. Would you like details?')
assert rt.store.read('followup_turn',f.digest('origin:inquiry'))['disposition']=='no_commitment'
fu=rt.store.goal('fixture')[0]['followup'];assert fu['delivery_state']=='unknown' and fu['delivery_basis']['kind']=='reply'
reset_projection()
turn('cancel','What is the status? Cancel fixture.','The cancellation needs to be processed.')
plan=call({'kind':'reconcile'})
# Lexical continuation may be needed after the extra corruption fixtures.
while not any(x['id']=='fixture' and x['object_kind']=='goal' for x in plan['items']):
    plan=call({'kind':'reconcile','cursor':plan['next_cursor']})
item=next(x for x in plan['items'] if x['id']=='fixture')
assert not item['change'] and item['blocked_by']
call({'kind':'reconcile','mode':'apply','id':'fixture','object_kind':'goal','expected_revision':item['expected_revision'],'request_id':'blocked'},False)
turn('separate','Investigate the separate project.','The separate investigation remains ongoing.')
row=rt.store.read('followup_turn',f.digest('origin:separate'))
call({'kind':'review','candidate_id':row['id'],'expected_revision':row['revision'],'disposition':'unrelated','goal_ids':['fixture'],
      'reason':'Reviewed original request and final reply; separate project only','request_id':'scope-review'})
# Reviewing the newest unrelated turn cannot hide an older unresolved cancellation.
assert not rt.store.goal('fixture')[0]['followup'].get('delivery_basis')
vmod=importlib.import_module(pkg+'.views');cmod=importlib.import_module(pkg+'.content_io')
call({'kind':'reconcile','mode':'apply','id':'fixture','object_kind':'goal',
      'expected_revision':cmod.revision(vmod.canonical(rt.store.goal('fixture')[0])), 'request_id':'older-cancel-blocks'},False)
row=rt.store.read('followup_turn',f.digest('origin:cancel'))
call({'kind':'review','candidate_id':row['id'],'expected_revision':row['revision'],'disposition':'already_fulfilled',
      'reason':'Synthetic related request explicitly reviewed; no real execution exists','request_id':'related-reviewed'})
view=importlib.import_module(pkg+'.views');content=importlib.import_module(pkg+'.content_io')
g=rt.store.goal('fixture')[0]
call({'kind':'reconcile','mode':'apply','id':'fixture','object_kind':'goal','expected_revision':content.revision(view.canonical(g)),'request_id':'project-reviewed'})
assert not rt.store.all('notification')
assert f.snapshot(home)['due_total']==0
# A status-looking suffix cannot retire mixed instructions. No semantic review is issued.
reset_projection()
mixed_inputs = [
    '放弃 fixture，状态如何？', '状态如何？放弃 fixture',
    'fixture先搁置，状态如何？', '状态如何，fixture改成只读？',
    '状态如何？不做fixture了。', 'Abandon fixture，状态如何？',
    '状态如何？ Drop fixture.', 'What is the status? Shelve fixture.',
    'Forget fixture, what is the status?', 'How is fixture if we abandon it?',
    'What is the status?\n暂停 fixture', 'How is the other service?',
]
for i,text in enumerate(mixed_inputs):
    key='mixed-'+str(i)
    turn(key,text,'当前结果已记录。是否需要详细信息？' if i%2==0 else 'Current result is recorded.')
    row=rt.store.read('followup_turn',f.digest('origin:'+key));g=rt.store.goal('fixture')[0]
    assert row['disposition']=='pending' and not row.get('unrelated_goals'), (text,row)
    assert g['status']=='active' and not g['followup'].get('delivery_basis'), (text,g)
    assert f.snapshot(home)['due_total']==1, text
for i,text in enumerate(['状态如何？','What is the status?','目前状态如何？']):
    key='pure-'+str(i);turn(key,text,'Services are running. Would you like more detail?')
    assert rt.store.read('followup_turn',f.digest('origin:'+key))['disposition']=='no_commitment'
    assert f.snapshot(home)['due_total']==1  # older mixed instructions still hold
native.close();rt.close()
print(json.dumps({'ok':True,'native_completed_interrupted_failed_missing':True,'corrupt_durable_unknown':True,
                 'negative_and_mention_do_not_handoff':True,'explicit_reviewed_handoff_replay':True,
                 'unrelated_finished_inquiry_unblocks':True,'related_input_blocks':True,'scoped_semantic_review':True,
                 'duplicate_replay_rollback':True,'dry_run_byte_identical':True,'scope_child_protected':True,
                 'mixed_input_cases':len(mixed_inputs),'pure_inquiry_cases':3,'older_instructions_still_block':True,
                 'model_calls':0,'sends':0}))
