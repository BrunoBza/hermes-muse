"""Dashboard-only profile selection and isolated official plugin lifecycle calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from .content_io import DomainError, revision
from .views import Views, canonical

PLUGIN = 'hermes-muse'
_locks_guard = threading.Lock()
_locks = {}


def resolve(name):
    from hermes_cli.profiles import get_profile_dir, list_profile_names, normalize_profile_name
    from hermes_constants import get_default_hermes_root, get_hermes_home
    if not isinstance(name, str) or normalize_profile_name(name) != name or name not in list_profile_names():
        raise DomainError('not_found', 'Select a registered profile on this Hermes host')
    root = get_default_hermes_root(home=get_hermes_home()).resolve()
    home = get_profile_dir(name).resolve()
    if name == 'default' and home != root:
        raise DomainError('profile_mismatch', 'Default root resolution changed')
    return home


def state(name):
    from pm.plugins_state import read_home_selection
    from hermes_cli.plugins import parse_manifest_file
    home = resolve(name)
    # PM's public selection reader does not seed SOUL/config backups or mutate
    # process globals; generic load_config_readonly is not side-effect-free.
    selection = (read_home_selection(home) or {}).get('plugins', {})
    enabled = PLUGIN in selection.get('enabled', []) and PLUGIN not in selection.get('disabled', [])
    path = home/'plugins'/PLUGIN
    manifest = parse_manifest_file(path/'plugin.yaml', path, 'user', '') if (path/'plugin.yaml').is_file() else None
    try:
        raw = Views(home).files.read('install.json')
    except FileNotFoundError:
        raw = b''
    row = {'name': name, 'installed': manifest is not None, 'enabled': bool(manifest and enabled),
           'version': manifest.version if manifest else None, 'managed_by': 'Hermes' if name == 'default' else 'Muse page',
           'read_only': name == 'default', 'initialized': bool(raw)}
    row['revision'] = revision(canonical([row, revision(raw)]))
    return row


def profiles():
    from hermes_cli.profiles import list_profile_names
    return {'profiles': [state(name) for name in list_profile_names()],
            'host_scope': 'This Hermes instance only; select a profile before viewing its content'}


def selected_view(name):
    row = state(name)
    if not row['installed'] or not row['enabled']:
        raise DomainError('not_installed', 'Muse is not installed and enabled in this profile')
    return Views(resolve(name))


def change(name, data):
    """Called only after the router's actual host session authentication."""
    home = resolve(name)
    from hermes_constants import get_default_hermes_root
    if name == 'default' or home == get_default_hermes_root(home=home).resolve():
        raise DomainError('permission_denied', 'Default Muse is managed by Hermes; this page cannot install, disable or remove it')
    if not isinstance(data, dict) or set(data) != {'operation', 'expected_revision', 'request_id'}:
        raise DomainError('invalid_argument', 'Use operation, expected_revision and request_id')
    if data['operation'] not in {'enable', 'disable'} or not isinstance(data['expected_revision'], str):
        raise DomainError('invalid_argument', 'Choose enable or disable; data removal is not supported')
    if not isinstance(data['request_id'], str) or not 1 <= len(data['request_id']) <= 128:
        raise DomainError('invalid_argument', 'request_id must be 1..128 characters')
    with _locks_guard:
        lock = _locks.setdefault(str(home), threading.Lock())
    with lock:
        # Fresh interpreter: no profile-sensitive PluginManager/cron/module cache is shared.
        script = Path(__file__).resolve().parents[1]/'dashboard/manage_profile.py'
        bootstrap = 'import runpy,sys;sys.path=' + repr(sys.path) + ';runpy.run_path(' + repr(str(script)) + ',run_name="__main__")'
        from tools.environments.local import served_profile_child_env
        env = {**served_profile_child_env(target_home=home, inherit_credentials=True), 'HERMES_HOME': str(home), 'HERMES_PROFILE': name,
               'HERMES_DISABLE_LAZY_INSTALLS': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
        payload = {**data, 'profile_name': name}
        process = subprocess.Popen([sys.executable, '-c', bootstrap], env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   start_new_session=os.name != 'nt')
        try:
            output, _errors = process.communicate(json.dumps(payload), timeout=180)
        except subprocess.TimeoutExpired as exc:
            if os.name != 'nt':
                import signal
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.communicate()
            raise DomainError('outcome_unknown', 'Profile operation timed out; refresh its state before retrying the same request') from exc
        try:
            result = json.loads(output.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise DomainError('outcome_unknown', 'Profile operation did not return a valid lifecycle receipt; refresh state') from exc
        if process.returncode or not result.get('ok'):
            raise DomainError(result.get('code', 'source_unavailable'), result.get('error', 'Hermes profile operation failed'))
        return result['result']


def _resume_page_pauses(host, store):
    from cron.jobs import resume_job
    import time
    manifest = host.manifest()
    prepared = manifest.get('preparation') or {}
    if prepared.get('origin') != 'dashboard':
        return []
    resumed = []
    for key, entry in prepared.get('jobs', {}).items():
        job = host.owned_job(key)
        owned = manifest['jobs'].get(key, {})
        if not entry.get('paused_by_prepare') or not job or job.get('enabled') or job.get('paused_reason') != 'Muse explicit disable preparation':
            continue
        if owned.get('owner'):
            goal, _ = store.goal(owned['owner'])
            if goal['status'] != 'active' or goal.get('research_review_at', 0) <= time.time() or (owned.get('expires') or float('inf')) <= time.time():
                continue
        resume_job(key)
        resumed.append(key)
    manifest['last_dashboard_preparation'] = prepared
    manifest.pop('preparation', None)
    host.save_manifest(manifest)
    return resumed


def operate(data):
    """One target profile, one process; never expose this as an agent action."""
    from hermes_constants import get_hermes_home, get_default_hermes_root
    from hermes_cli.plugins_cmd import dashboard_set_agent_plugin_enabled
    from hermes_cli.plugins_activation import activate_plugin_now
    from .host import HermesHost
    from .store import Store
    from .installation import prepare_owned
    name = data['profile_name']
    home = resolve(name)
    if name == 'default' or home == get_default_hermes_root(home=home).resolve() or home != get_hermes_home().resolve():
        raise DomainError('permission_denied', 'Only the selected non-default profile can be managed')
    current = state(name)
    desired = data['operation'] == 'enable'
    if current['enabled'] == desired and (current['installed'] or not desired):
        return {'profile': current, 'unchanged': True}
    pending = {}
    if current['initialized']:
        pending = json.loads((home/'muse/install.json').read_text()).get('preparation') or {}
    retry = pending.get('origin') == 'dashboard' and pending.get('request_id') == data['request_id'] and not desired
    if current['revision'] != data['expected_revision'] and not retry:
        raise DomainError('revision_conflict', 'Profile state changed; refresh before changing it')
    if desired:
        if not current['installed']:
            from hermes_cli.plugins_cmd_install import dashboard_install_plugin
            source = get_default_hermes_root(home=home).resolve()/'plugins'/PLUGIN
            pin = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
            receipt = dashboard_install_plugin(source.as_uri(), force=False, enable=True, ref=pin)
        else:
            receipt = dashboard_set_agent_plugin_enabled(PLUGIN, enabled=True)
        if not receipt.get('ok'):
            raise DomainError('source_unavailable', receipt.get('error', 'Official installer refused the operation'))
        from tools.registry import registry
        entry = registry.get_entry('muse_manage')
        runtime = getattr(getattr(entry, 'handler', None), '__self__', None)
        if runtime is None or runtime.home.resolve() != home:
            raise DomainError('outcome_unknown', 'Hermes enabled the plugin but initialization was not confirmed; refresh before retrying')
        store, host = runtime.store, runtime.host
        from importlib import import_module
        # Use the loaded plugin's own reentrant lock, not a second module namespace.
        loaded_host = import_module(host.__class__.__module__)
        with loaded_host.file_lock(store.path('install.lock')):
            resumed = _resume_page_pauses(host, store)
        activation = activate_plugin_now(PLUGIN, in_process=False)
        return {'profile': state(name), 'activation': activation, 'resumed_owned_ids': resumed}
    store = Store(home)
    host = HermesHost(store, home/'plugins'/PLUGIN)
    prepared = prepare_owned(home, store, host, {'operation': 'disable', 'request_id': data['request_id'],
        'expected_revision': pending['expected_revision'] if retry else Views(home).object('installation', 'current')[2]}, origin='dashboard')
    if prepared['partial']:
        return {'profile': state(name), 'preparation': prepared, 'partial': True, 'requires_retry': True}
    receipt = dashboard_set_agent_plugin_enabled(PLUGIN, enabled=False)
    if not receipt.get('ok'):
        raise DomainError('source_unavailable', receipt.get('error', 'Official disable failed'))
    from gateway.control_socket import reload_gateway_plugins
    activation = reload_gateway_plugins(get_default_hermes_root(home=home), profile_home=home)
    return {'profile': state(name), 'preparation': prepared, 'activation': activation,
            'restart_required': not bool(activation and activation.get('reloaded')), 'data_retained': True}
