"""Dashboard-only read-only profile listing and selection; lifecycle stays with Hermes."""
from .content_io import DomainError, revision
from .views import Views, canonical

PLUGIN = 'hermes-muse'


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
           'version': manifest.version if manifest else None, 'managed_by': 'Hermes',
           'read_only': True, 'initialized': bool(raw)}
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

