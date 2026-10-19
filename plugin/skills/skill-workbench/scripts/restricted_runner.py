"""Per-invocation workspace-only Codex runner; never installs profiles or copies credentials."""
import json
import os
import signal
import subprocess
import sys
import uuid
from pathlib import Path

PROFILE = 'skill-workbench-local'


def environments(work, private, inherited):
    home = Path(inherited['HOME']).resolve()
    client_home = Path(inherited.get('CODEX_HOME', home / '.codex')).resolve()
    client = {'HOME': str(home), 'CODEX_HOME': str(client_home), 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
              'TMPDIR': str(work.parent / 'client-tmp'), 'LANG': 'en_US.UTF-8', 'SHELL': '/bin/zsh'}
    for key in ('CODEX_PERMISSION_PROFILE', 'CODEX_SANDBOX_NETWORK_DISABLED'):
        if key in inherited:
            client[key] = inherited[key]
    tool = {'HOME': str(work), 'TMPDIR': str(work / '.runner-tmp'), 'LANG': 'en_US.UTF-8',
            'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'PYTHONDONTWRITEBYTECODE': '1', 'SHELL': '/bin/zsh'}
    return client, tool


def overrides(work, private, client, tool):
    # CLI control-plane auth remains outside the sandboxed command process.
    filesystem = {':root': 'deny', ':minimal': 'read', ':tmpdir': 'deny', ':slash_tmp': 'deny',
                  str(private): 'deny', client['CODEX_HOME']: 'deny'}
    settings = {'default_permissions': PROFILE,
                f'permissions.{PROFILE}.extends': ':workspace',
                f'permissions.{PROFILE}.filesystem': filesystem,
                f'permissions.{PROFILE}.network.enabled': False,
                'approval_policy': 'never', 'web_search': 'disabled', 'allow_login_shell': False,
                'shell_environment_policy.inherit': 'none',
                'shell_environment_policy.ignore_default_excludes': False,
                'shell_environment_policy.experimental_use_profile': False,
                'shell_environment_policy.set': tool,
                'sqlite_home': str(Path(client['TMPDIR']).parent / 'client-state'),
                'history.persistence': 'none', 'analytics.enabled': False}
    for feature in ('apps', 'plugins', 'remote_plugin', 'multi_agent', 'multi_agent_v2',
                    'shell_snapshot', 'skill_mcp_dependency_install', 'skill_search', 'browser_use',
                    'browser_use_external', 'in_app_browser', 'computer_use', 'hooks', 'memories',
                    'external_agent_memory_import'):
        settings[f'features.{feature}'] = False
    # json is valid TOML for these primitive values, arrays and inline tables need TOML syntax.
    def value(v):
        if isinstance(v, dict):
            return '{' + ','.join(json.dumps(k) + '=' + value(x) for k, x in v.items()) + '}'
        return json.dumps(v)
    return [item for key, v in settings.items() for item in ('-c', key + '=' + value(v))]


# This probe never reads credential bytes. It only tests opening the existing auth file.
PROBE = r"""
import errno,json,os,pathlib,socket,sys
work,canary,auth=map(pathlib.Path,sys.argv[1:])
result={}
def denied(action):
    try: action(); return False
    except OSError as e: return e.errno in (errno.EACCES,errno.EPERM)
result['outside_read_denied']=denied(lambda:canary.read_bytes())
result['outside_write_denied']=denied(lambda:canary.open('wb').close())
result['auth_open_denied']=denied(lambda:auth.open('rb').close())
link=work/'.runner-escape'
link.symlink_to(canary)
try: result['symlink_read_denied']=denied(lambda:link.read_bytes())
finally: link.unlink()
local=work/'.runner-probe'
local.write_text('fixture')
result['workspace_read_write']=local.read_text()=='fixture'
local.unlink()
sock=socket.socket();sock.settimeout(0.5)
try: result['network_denied']=denied(lambda:sock.connect(('127.0.0.1',9)))
finally: sock.close()
result['clean_environment']=not any(any(s in k.upper() for s in ('TOKEN','SECRET','API_KEY')) for k in os.environ)
print(json.dumps(result))
"""


def prepare(executable, work, private, inherited, timeout):
    if sys.platform != 'darwin':
        raise ValueError('workspace-only runner supports validated macOS Seatbelt only')
    work, private = work.resolve(), private.resolve()
    client, tool = environments(work, private, inherited)
    auth = Path(client['CODEX_HOME']) / 'auth.json'
    metadata = json.loads(auth.read_text())
    if not isinstance(metadata, dict) or metadata.get('auth_mode') != 'chatgpt' or metadata.get('OPENAI_API_KEY'):
        raise ValueError('restricted runner requires existing ChatGPT sign-in, not API-key auth')
    if (any('.codex' in p.relative_to(work).parts or p.name == '.mcp.json' for p in work.rglob('*')) or
            any((parent / name).exists() or (parent / name).is_symlink()
                for parent in (work, *work.parents) for name in ('.codex', '.mcp.json'))):
        raise ValueError('project client configuration is not supported by restricted runner')
    if any(Path(p).exists() for p in ('/etc/codex/config.toml', '/etc/codex/requirements.toml')):
        raise ValueError('managed client configuration requires a separate isolation audit')
    if private.is_relative_to(work) or auth.is_relative_to(work):
        raise ValueError('client/grader state must be outside workspace')
    if not Path(executable).is_absolute() or not Path(executable).is_file():
        raise ValueError('existing absolute Codex executable required')
    Path(tool['TMPDIR']).mkdir(exist_ok=True)
    Path(client['TMPDIR']).mkdir(exist_ok=True)
    canary = private / ('canary-' + uuid.uuid4().hex)
    canary.write_text('synthetic-only')
    settings = overrides(work, private, client, tool)
    command = [executable, *settings, 'sandbox', '--include-managed-config', '-P', PROFILE,
               '-C', str(work), '--', '/usr/bin/env', '-i',
               *(k + '=' + v for k, v in tool.items()), tool['SHELL'], '-f', '-c', 'exec "$@"',
               'runner-preflight', '/usr/bin/python3', '-c', PROBE,
               str(work), str(canary), str(auth)]
    process = None
    result = {'passed': False}
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=client, start_new_session=True)
        out, err = process.communicate(timeout=min(timeout, 20))
        (private / 'preflight-stderr.txt').write_bytes(err)
        if process.returncode == 0:
            checks = json.loads(out)
            expected = {'outside_read_denied', 'outside_write_denied', 'auth_open_denied',
                        'symlink_read_denied', 'workspace_read_write', 'network_denied', 'clean_environment'}
            result = {'passed': isinstance(checks, dict) and set(checks) == expected and
                      all(v is True for v in checks.values()), 'checks': checks}
        if not result['passed']:
            raise ValueError('restricted runner preflight failed; no model call permitted')
    finally:
        if process is not None:
            if process.poll() is None:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            process.communicate()
        canary.unlink(missing_ok=True)
        (work / '.runner-escape').unlink(missing_ok=True)
        (work / '.runner-probe').unlink(missing_ok=True)
        (private / 'preflight.json').write_text(json.dumps(result, indent=2) + '\n')
    return settings, client
