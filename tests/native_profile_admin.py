"""Actual authenticated host routes and official installer in isolated custom homes."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import json


def worker(home):
    import shutil
    import hashlib
    from concurrent.futures import ThreadPoolExecutor
    from unittest.mock import patch
    repo=Path(__file__).resolve().parents[1]
    sys.path[:0]=[str(repo),os.environ['HERMES_SOURCE']]
    (home/'config.yaml').write_text('plugins:\n  enabled: [hermes-muse]\n  isolation: in-process\ntimezone: UTC\n')
    source=home/'plugins/hermes-muse'
    source.mkdir(parents=True)
    files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],cwd=repo,text=True).splitlines()
    for name in files:
        if name.startswith('.serena/') or not (repo/name).is_file():continue
        (source/name).parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(repo/name,source/name)
    subprocess.run(['git','init','-q','-b','main'],cwd=source,check=True)
    subprocess.run(['git','add','.'],cwd=source,check=True)
    subprocess.run(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','-c','core.hooksPath=/dev/null','commit','-qm','synthetic tested source'],cwd=source,check=True)
    from hermes_muse.store import Store
    from hermes_muse.host import HermesHost,profile_scope
    from hermes_muse.service import Companion
    default_store=Store(home); default_host=HermesHost(default_store,source);default_host.initialize()
    default_service=Companion(default_store,default_host)
    default_service.signal('fixture','default-session','Maintain synthetic goal default-goal')
    default_service.goal_create(dict(id='default-goal',signal_id='fixture',title='Default private fixture',description='Default only',completion_criteria='Read'))
    target=home/'profiles/cedar';target.mkdir(parents=True)
    (target/'config.yaml').write_text('plugins:\n  enabled: []\ntimezone: UTC\nterminal:\n  backend: docker\n')
    other=home/'profiles/orchid';other.mkdir(parents=True)
    (other/'config.yaml').write_text('plugins:\n  enabled: []\ntimezone: UTC\n')
    from cron.jobs import list_jobs,create_job,pause_job
    with profile_scope(target):
        user_job=create_job(prompt='Synthetic user subscription',schedule='every 2h',name='user-owned',deliver='local')
    def hashes(path):return {str(p.relative_to(path)):hashlib.new('sha256',p.read_bytes()).hexdigest() for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts}
    protected=hashes(other)
    from hermes_cli.web_server import app
    from fastapi.testclient import TestClient
    client=TestClient(app,base_url='http://127.0.0.1')
    headers={'Authorization':'Bearer isolated-profile-admin'}
    base='/api/plugins/hermes-muse'
    def profiles():
        r=client.get(base+'/profiles?profile=default',headers=headers)
        assert r.status_code==200,r.text
        return {x['name']:x for x in r.json()['profiles']}
    def post(name,operation,revision,key):
        return client.post(base+'/profiles/'+name+'?profile=default',headers=headers,json={'operation':operation,'expected_revision':revision,'request_id':key})
    assert client.get(base+'/profiles?profile=default').status_code==401
    assert client.post(base+'/profiles/cedar?profile=default',json={}).status_code==401
    rows=profiles();assert set(rows)=={'default','cedar','orchid'}
    assert rows['default']['read_only'] and rows['default']['managed_by']=='Hermes'
    assert not rows['cedar']['installed'] and not (target/'muse').exists()
    before=hashes(home/'muse')
    for op in ('enable','disable','remove'):
        r=post('default',op,rows['default']['revision'],'forbidden-'+op)
        assert r.status_code==403,r.text
    assert hashes(home/'muse')==before
    assert client.get(base+'/goals?profile=default&selected_profile=cedar',headers=headers).status_code==404
    original_popen=subprocess.Popen
    observed=[]
    def checked_popen(*args,**kwargs):
        env=kwargs.get('env',{})
        if env.get('HERMES_PROFILE')=='cedar':
            assert env.get('OPENAI_API_KEY')!='parent-only-synthetic'
            assert env.get('HERMES_HOME')==str(target)
            observed.append(True)
        return original_popen(*args,**kwargs)
    with patch.dict(os.environ,{'OPENAI_API_KEY':'parent-only-synthetic'}), patch('subprocess.Popen',side_effect=checked_popen):
        response=post('cedar','enable',rows['cedar']['revision'],'enable-one')
    assert observed
    assert response.status_code==200,response.text
    assert response.json()['profile']['enabled']
    with profile_scope(target):
        jobs=list_jobs(include_disabled=True)
        assert len(jobs)==7,(len(jobs),jobs)
        store=Store(target); host=HermesHost(store,target/'plugins/hermes-muse')
        manifest=host.manifest();identity=manifest['installation_id'];ids=set(manifest['fixed'].values());assert len(ids)==6
        pauses=sorted(ids);pause_job(pauses[0],reason='Synthetic user pause')
        service=Companion(store,host);service.signal('fixture','cedar-session','Maintain synthetic goal default-goal')
        service.goal_create(dict(id='default-goal',signal_id='fixture',title='Cedar private fixture',description='Cedar only',completion_criteria='Read'))
        original={j['id']:{k:j.get(k) for k in ('schedule','deliver','model','workdir')} for j in list_jobs(include_disabled=True)}
    # Concurrent profile GETs must not borrow process/global caches or content.
    def get(name):
        r=client.get(base+'/goals/default-goal?profile=default&selected_profile='+name,headers=headers)
        assert r.status_code==200,r.text
        return r.json()
    env_before=dict(os.environ)
    with ThreadPoolExecutor(max_workers=4) as pool:
        values=list(pool.map(get,['default','cedar']*5))
    assert [v['metadata']['title'] for v in values]==['Default private fixture','Cedar private fixture']*5
    assert os.environ==env_before
    wrong=client.get(base+'/goals/default-goal?profile=default&selected_profile=cedar&scope_token='+values[0]['scope_token'],headers=headers)
    assert wrong.status_code==403
    rows=profiles(); r=post('cedar','disable',rows['cedar']['revision'],'disable-one');assert r.status_code==200,r.text
    assert not r.json()['profile']['enabled'] and r.json()['data_retained']
    with profile_scope(target):
        after=list_jobs(include_disabled=True)
        assert all(not j['enabled'] for j in after if j['id'] in ids)
        assert next(j for j in after if j['id']==user_job['id'])['enabled']
    assert client.get(base+'/goals?profile=default&selected_profile=cedar',headers=headers).status_code==404
    rows=profiles();r=post('cedar','enable',rows['cedar']['revision'],'enable-two');assert r.status_code==200,r.text
    with profile_scope(target):
        after=list_jobs(include_disabled=True)
        assert len(after)==7
        assert host.manifest()['installation_id']==identity and set(host.manifest()['fixed'].values())==ids
        assert not next(j for j in after if j['id']==pauses[0])['enabled']
        assert all(j['enabled'] for j in after if j['id']!=pauses[0])
        assert original=={j['id']:{k:j.get(k) for k in ('schedule','deliver','model','workdir')} for j in after}
    assert get('cedar')['metadata']['title']=='Cedar private fixture'
    assert post('cedar','enable',rows['cedar']['revision'],'enable-two').status_code==200
    assert hashes(other)==protected, {k:(protected.get(k),hashes(other).get(k)) for k in set(protected)|set(hashes(other)) if protected.get(k)!=hashes(other).get(k)}
    assert get('default')['metadata']['title']=='Default private fixture'
    print(json.dumps({'profile_admin':'PASS','official_installer':True,'custom_home':True,'default_backend_refusals':3,'six_jobs_preserved':True,'user_job_and_pause_preserved':True,'ids_cadence_targets_preserved':True,'data_retained':True,'concurrent_profile_scope_no_env_mutation':True,'other_profile_unchanged':True,'no_model_calls':True}))


if __name__=='__main__':
    assert os.environ.get('TMPDIR')
    if len(sys.argv)>1:
        worker(Path(os.environ['HERMES_HOME']))
    else:
        with tempfile.TemporaryDirectory(prefix='muse-admin-fixture-') as directory:
            env={**os.environ,'HERMES_HOME':directory,'TMPDIR':directory,'HERMES_DATA_DIR_SUFFIX':'-muse-isolated-test','HERMES_IGNORE_USER_CONFIG':'1','HERMES_DISABLE_LAZY_INSTALLS':'1','PYTHONDONTWRITEBYTECODE':'1','HERMES_DASHBOARD_SESSION_TOKEN':'isolated-profile-admin'}
            result=subprocess.run([sys.executable,__file__,'--worker'],env=env)
        print(json.dumps({'owned_home_removed_after_process_exit':not Path(directory).exists(),'services_started':0}))
        raise SystemExit(result.returncode)
