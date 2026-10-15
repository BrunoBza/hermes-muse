"""Native registry/SessionDB boundary checks; isolated home, no model or sends."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

if len(sys.argv) == 1:
    assert os.environ.get('TMPDIR')
    with tempfile.TemporaryDirectory(prefix='muse-native-rebind-') as home:
        env = dict(os.environ, HERMES_HOME=home, HERMES_IGNORE_USER_CONFIG='1', HERMES_DISABLE_LAZY_INSTALLS='1', PYTHONDONTWRITEBYTECODE='1')
        raise SystemExit(subprocess.call([sys.executable, __file__, home], env=env))

home=Path(sys.argv[1]).resolve();repo=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(repo),str(repo/'tests'),os.environ['HERMES_SOURCE']]
(home/'config.yaml').write_text('plugins:\n  enabled: [hermes-muse]\ntimezone: UTC\n')
shutil.copytree(repo,home/'plugins/hermes-muse',ignore=shutil.ignore_patterns('.git','.serena','__pycache__'))
from hermes_cli.plugins import discover_plugins
from hermes_state import SessionDB
from model_tools import handle_function_call
from tools.registry import registry
from agent.delegation_context import delegated_child_context
from tools.async_delegation import _persist_dispatch, _persist_completion
from tool_client import transport
from hermes_muse.content_io import revision
from hermes_muse.views import canonical

discover_plugins(force=True);rt=registry.get_entry('muse_manage').handler.__self__
db=SessionDB(db_path=home/'state.db');db.create_session('origin',source='cli',chat_type='private');db.create_session('other',source='cli',chat_type='private')
rt.service.signal('u','origin','Complete the fixture')
rt.service.goal_create(dict(id='g',title='Fixture',description='Work',completion_criteria='Artifact',signal_id='u'))
g,b=rt.store.goal('g');g['followup'].update(result_state='verified',verification={'verified_at':time.time()+1,'summary':'later review'});rt.store.save_goal(g,b)
mid=db.append_message('origin','assistant','Historical completed fixture result')
# SessionDB append returns the row id on the official host.
assert type(mid) is int

def call(data,ok=True,session='origin',task=None):
    raw=handle_function_call('muse_manage',transport({'action':'followup_update','data':data}),session_id=session,turn_id='u',tool_call_id=uuid.uuid4().hex,task_id=task,enabled_toolsets=['muse'])
    assert len(raw.encode())<=262144
    result=json.loads(raw);assert result['ok']==ok,result
    return result.get('result') if ok else result

def args(**kw):
    g=rt.store.goal('g')[0]
    return dict(kind='rebind',binding='reply',goal_id='g',message_id=mid,message_hash=revision(b'Historical completed fixture result'),expected_revision=rt.store.goal('g',with_fingerprint=True)[2],request_id=uuid.uuid4().hex,reason='Parent reviewed this exact historical result',**kw)

request=args();result=call(request);assert call(request)==result
with delegated_child_context('fixture-child'):assert call(request,False)['code']=='permission_denied'
assert call(request,False,task='cron:job:execution')['code']=='permission_denied'
assert call(args(),False,session='other')['code']=='permission_denied'
assert call({**args(),'scope_token':'foreign'},False)['code']=='profile_mismatch'
rollback=dict(kind='reconcile',mode='rollback',repair_id=result['repair_id'],expected_revision=result['revision'],request_id='rollback')
assert call(rollback,False,task='cron:job:execution')['code']=='permission_denied'
# A rejected request has its own key; retry original valid arguments with a fresh key.
rollback['request_id']='rollback-parent';call(rollback)
assert rt.store.read('followup_reply',result['reply_id']) is None
result=call(args());g=rt.store.goal('g')[0]
call(dict(kind='handoff',goal_id='g',expected_revision=g['followup']['revision'],reply_id=result['reply_id'],reason='Exact historical result reviewed as delivered',request_id='handoff'))
assert rt.store.goal('g')[0]['followup']['delivery_state']=='unknown'
# Second goal keeps interrupted original and binds a natively completed successor.
rt.service.goal_create(dict(id='successor-goal',title='Fixture',description='Work',completion_criteria='Artifact',signal_id='u'))
g,b=rt.store.goal('successor-goal');g['followup'].update(intent_id='old-intent',receipt_id='old',owner={'kind':'native_delegation','id':'deleg_old'},execution_state='outcome_unknown');rt.store.save_goal(g,b)
rt.store.write('followup_receipt','old',dict(id='old',session_id='origin',native_status='interrupted',terminal=True,failed=True,owner=g['followup']['owner']))
from hermes_cli.plugins import invoke_hook
invoke_hook('post_tool_call',tool_name='delegate_task',args={'goal':'Fixture successor'},result=json.dumps({'status':'dispatched','delegation_id':'deleg_successor'}),session_id='origin',turn_id='u',tool_call_id='successor-call')
_persist_dispatch({'delegation_id':'deleg_successor','origin_session_id':'origin','dispatched_at':time.time()})
_persist_completion({'delegation_id':'deleg_successor','status':'completed'},{'results':[{'status':'completed'}]})
receipt=next(x for x in rt.store.all('followup_receipt') if (x.get('owner') or {}).get('id')=='deleg_successor')
text=json.dumps({'delegation_id':'deleg_successor','status':'completed','results':[{'status':'completed','response':'fixture result'}]})
mid2=db.append_message('origin','tool',text,tool_name='delegate_task',tool_call_id='successor-call')
request=dict(kind='rebind',binding='successor',goal_id='successor-goal',expected_revision=rt.store.goal('successor-goal',with_fingerprint=True)[2],receipt_id=receipt['id'],evidence_refs=[dict(kind='native_message',session_id='origin',message_id=mid2,hash=revision(text.encode()))],reason='Parent associates successor result with unchanged goal criteria',request_id='successor-bind')
r=call(request);assert call(request)==r
assert rt.store.read('followup_receipt','old')['native_status']=='interrupted'
call(dict(kind='verification',goal_id='successor-goal',expected_revision=rt.store.goal('successor-goal')[0]['followup']['revision'],result_state='verified',sources=['message:'+str(mid2)],evidence_refs=request['evidence_refs'],verified_at=time.time(),summary='Fixture result',request_id='verify-successor'))
print(json.dumps({'native_registry':True,'reply_and_successor':True,'replay':True,'rollback':True,'child_cron_foreign_scope_rejected':True,'original_interrupted_preserved':True,'max_response_bytes':262144}))
rt.close();db.close()
