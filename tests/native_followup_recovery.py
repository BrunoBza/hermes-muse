"""Real native registry, lifecycle hooks, SessionDB and delegation persistence; no LLM/sends."""
import importlib
import json
import os
from pathlib import Path
import shutil
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
# Existing accepted+verified result; finish hook forms handoff without send/confirmed.
rt.service.signal('accepted','origin','Research the fixture')
rt.service.goal_create({'id':'fixture','signal_id':'accepted','title':'Fixture','description':'Research','completion_criteria':'Verified artifact'})
g,b=rt.store.goal('fixture');g['followup'].update(execution_state='finished',result_state='verified',verification={'verified_at':time.time()-10,'summary':'Verified fixture artifact'})
rt.store.save_goal(g,b)
native.append_message('origin','assistant','Verified fixture artifact')
invoke_hook('post_llm_call',session_id='origin',turn_id='accepted',assistant_response='Verified fixture artifact',conversation_history=[])
invoke_hook('on_session_end',session_id='origin',turn_id='accepted',completed=True,failed=False,interrupted=False)
fu=rt.store.goal('fixture')[0]['followup'];assert fu['delivery_state']=='unknown' and fu['delivery_basis']['kind']=='reply',fu
assert not rt.store.all('notification')
assert f.snapshot(home)['due_total']==0
native.close();rt.close()
print(json.dumps({'ok':True,'native_completed_interrupted_failed_missing':True,'hooks_auto_converge':True,'duplicate_replay_rollback':True,'dry_run_byte_identical':True,'scope_child_protected':True,'ordinary_question':True,'handoff_unconfirmed':True,'model_calls':0,'sends':0}))
