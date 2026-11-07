"""Portable Docker demonstration, controlled from Linux/WSL without a controller container."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile

LAB = Path(__file__).resolve().parent
REPO = LAB.parent
STATE = Path(os.environ.get('LAB_STATE_DIR', Path.home()/'.local/state/cpnginx-lab')).resolve()
IMAGE = 'cpnginx-lab-ubuntu:local'
VAULT_IMAGE = 'hashicorp/vault:1.16.3'
GIT_URL = 'https://github.com/paulitoop/cpnginx.git'
VAULT_URL = 'http://127.0.0.1:18200'
SECRET_PATH = 'cpnginx/data/demo/client'
os.environ['LAB_STATE_DIR'] = str(STATE)
os.umask(0o077)


class LabError(RuntimeError):
    pass


def run(args, capture=False, check=True, **kwargs):
    result = subprocess.run([str(x) for x in args], capture_output=capture, text=True, **kwargs)
    if check and result.returncode:
        if capture:
            print((result.stderr or '')[-2000:], file=sys.stderr)
        raise LabError(f'Command failed: {Path(str(args[0])).name} (exit {result.returncode})')
    return result


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')
    path.chmod(0o600)


def load(path):
    return json.loads(path.read_text())


def compose(*args, capture=False, check=True, two=False):
    command = ['docker', 'compose', '-p', 'cpnginx-demo', '-f', LAB/'compose.yaml']
    if two:
        command += ['--profile', 'two']
    return run(command + list(args), capture=capture, check=check)


def require_prepared():
    if not (STATE/'manifest.json').exists():
        raise LabError('Run ./lab/lab.sh prepare first')


def api(path, body=None, method=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['X-Vault-Token'] = token
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(VAULT_URL+'/v1/'+path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as exc:
        # Never include a request body or token in errors.
        raise LabError(f'Vault {path}: HTTP {exc.code}') from None
    except (urllib.error.URLError, TimeoutError):
        raise LabError('Vault is unavailable; start the lab and check port 18200') from None


def root_token():
    return load(STATE/'vault-init.json')['root_token']


def bootstrap_vault():
    init_file = STATE/'vault-init.json'
    if not api('sys/init')['initialized']:
        save(init_file, api('sys/init', {'secret_shares': 1, 'secret_threshold': 1}))
    if not init_file.exists():
        raise LabError('This Vault volume has no matching local initialization file; restore it before continuing')
    init = load(init_file)
    if api('sys/seal-status')['sealed']:
        api('sys/unseal', {'key': init['keys_base64'][0]})
    token = init['root_token']
    mounts = api('sys/mounts', token=token)
    if 'cpnginx/' not in mounts:
        api('sys/mounts/cpnginx', {'type': 'kv', 'options': {'version': '2'}}, token=token)
    auth = api('sys/auth', token=token)
    if 'approle/' not in auth:
        api('sys/auth/approle', {'type': 'approle'}, token=token)
    api('sys/policies/acl/cpnginx-demo', {'policy': 'path "cpnginx/data/demo/*" { capabilities = ["read"] }'}, method='PUT', token=token)
    api('auth/approle/role/cpnginx-demo', {'token_policies': ['cpnginx-demo'], 'token_ttl': '1h', 'token_max_ttl': '4h', 'secret_id_ttl': '24h'}, token=token)
    role_id = api('auth/approle/role/cpnginx-demo/role-id', token=token)['data']['role_id']
    secret_id = api('auth/approle/role/cpnginx-demo/secret-id', {}, token=token)['data']['secret_id']
    save(STATE/'approle.json', {'role_id': role_id, 'secret_id': secret_id})


def certificate_info(path):
    args = ['openssl', 'x509', '-in', path, '-noout', '-serial', '-enddate']
    if b'-----BEGIN' not in path.read_bytes()[:100]:
        args += ['-inform', 'DER']
    output = run(args, capture=True).stdout
    valid = run(args[:2] + ['-in', path, '-noout', '-checkend', '86400'] + (['-inform', 'DER'] if '-inform' in args else []), capture=True, check=False)
    if valid.returncode:
        raise LabError(f'{path.name}: expired or expires within 24 hours; prepare --renew-certs')
    serial = next(line.split('=', 1)[1].strip() for line in output.splitlines() if line.startswith('serial='))
    return {'serial': '0x'+serial.upper(), 'description': output.strip()}


def prepare(args):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    for command in ['docker', 'git', 'ssh-keygen', 'ssh-keyscan', 'openssl']:
        if not shutil.which(command):
            raise LabError(f'{command} is missing. Enable Docker Desktop WSL integration and install Ubuntu prerequisites listed in lab/README.md')
    run(['docker', 'info', '--format', '{{.OSType}}'], capture=True)
    archive = Path(args.archive or os.environ.get('CPNGINX_CSP_ARCHIVE', '/opt/work/ansible/ansible-role-cpnginx_install-master/files/linux-amd64_deb.tgz'))
    if not archive.is_file():
        raise LabError('Provide the local CryptoPro distribution: prepare --archive /absolute/path/linux-amd64_deb.tgz')
    license_path = STATE/'server.license'
    if args.license_file:
        source = Path(args.license_file).expanduser().resolve()
        if not source.is_file():
            raise LabError('The TLS server license file does not exist')
        if source != license_path:
            shutil.copyfile(source, license_path)
    elif not license_path.exists():
        license_path.write_text('')
    license_path.chmod(0o600)
    build = STATE/'build'
    (build/'dist').mkdir(parents=True, exist_ok=True)
    shutil.copy2(archive, build/'dist/linux-amd64_deb.tgz')
    for folder in ['docker', 'files']:
        shutil.copytree(LAB/folder, build/folder, dirs_exist_ok=True)
    print('Building the Ubuntu/CryptoPro image (no keys or passwords are in the build context)...', flush=True)
    run(['docker', 'build', '-t', IMAGE, '-f', build/'docker/Ubuntu.Dockerfile', build])
    run(['docker', 'pull', VAULT_IMAGE])
    venv = STATE/'venv'
    if not (venv/'bin/python').exists():
        run([sys.executable, '-m', 'venv', venv])
    wheels = STATE/'wheels'
    wheels.mkdir(exist_ok=True)
    run([venv/'bin/pip', 'download', '-r', LAB/'requirements.lock.txt', '-d', wheels])
    run([venv/'bin/pip', 'install', '--no-index', '--find-links', wheels, '-r', LAB/'requirements.lock.txt'])
    roles = STATE/'roles'
    roles.mkdir(exist_ok=True)
    revisions = {}
    for name, repository in [('cryptogates.cpnginx_install', 'ansible-role-cpnginx_install'), ('cryptogates.cpnginx_configure', 'ansible-role-cpnginx_configure')]:
        destination = roles/name
        if args.local_roles:
            src = REPO.parent/repository
            if not src.is_dir():
                raise LabError(f'Local role source not found: {src}')
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(src, destination, ignore=shutil.ignore_patterns('.git', '__pycache__', 'reports'))
            revisions[repository] = 'local working tree'
        else:
            if not (destination/'.git').exists():
                if destination.exists():
                    shutil.rmtree(destination)
                run(['git', 'clone', '--depth', '1', f'https://github.com/paulitoop/{repository}.git', destination])
            else:
                run(['git', '-C', destination, 'fetch', 'origin', 'main'])
                run(['git', '-C', destination, 'reset', '--hard', 'FETCH_HEAD'])
            revisions[repository] = run(['git', '-C', destination, 'rev-parse', 'HEAD'], capture=True).stdout.strip()
    assets = STATE/'assets'
    assets.mkdir(exist_ok=True)
    if args.renew_certs or not (assets/'pins.json').exists():
        staging = STATE/'cert-generation'
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(mode=0o700)
        print('Generating fresh local GOST certificates in an isolated temporary container...', flush=True)
        run(['docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'python3',
             '-e', f'LAB_OWNER_UID={os.getuid()}', '-e', f'LAB_OWNER_GID={os.getgid()}',
             '-v', f'{staging}:/assets', IMAGE, '/usr/local/bin/generate-certificates.py'])
        for name in ['root', 'server', 'client']:
            certificate_info(staging/(name+'.cer'))
        if args.renew_certs:
            compose('down', two=True)
        # Replace old assets only after a complete, validated generation.
        if assets.exists():
            shutil.rmtree(assets)
        staging.rename(assets)
    server = certificate_info(assets/'server.cer')
    client = certificate_info(assets/'client.cer')
    certificate_info(assets/'root.cer')
    pins = load(assets/'pins.json')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive_out:
        archive_out.writestr('client.pfx', (assets/'client.pfx').read_bytes())
    save(STATE/'vault-payload.json', {'pfx': base64.b64encode(buffer.getvalue()).decode(), 'pin': pins['client']})
    example = f'''name: demo-mtls\ntarget_host: cpnginx.example.test\ntarget_port: 5101\nlisten_port: 30443\ncert_client: {SECRET_PATH}\ncert_client_serial: "{client['serial']}"\ncomment: "Portable GOST mTLS demo"\n'''
    (STATE/'demo-mtls.yaml').write_text(example)
    ssh_dir = STATE/'ssh'
    ssh_dir.mkdir(exist_ok=True)
    if not (ssh_dir/'id_ed25519').exists():
        run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', ssh_dir/'id_ed25519'])
    (STATE/'bin').mkdir(exist_ok=True)
    wrapper = STATE/'bin/vault'
    wrapper.write_text('#!/usr/bin/env bash\nset -euo pipefail\nexec python3 '+shlex.quote(str(LAB/'cli.py'))+' _vault "$@"\n')
    wrapper.chmod(0o700)
    (STATE/'ansible.cfg').write_text(f'[defaults]\nroles_path = {roles}\nhost_key_checking = True\nforks = 2\nretry_files_enabled = False\ninterpreter_python = auto_silent\n')
    save(STATE/'manifest.json', {'roles': revisions, 'server': server, 'client': client, 'image': run(['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}'], capture=True).stdout.strip()})
    print(f'Prepared. Local state: {STATE}\nVault JSON: {STATE}/vault-payload.json\nGitHub YAML: {STATE}/demo-mtls.yaml')
    print('Browser prerequisite: map cpnginx.example.test to 127.0.0.1 and explicitly trust assets/root.cer in your GOST browser. No Windows trust/hosts changes were made.')


def inventory(nodes):
    app = load(STATE/'approle.json')
    hosts = {f'proxy{i:02d}': {'ansible_host': '127.0.0.1', 'ansible_port': 2220+i} for i in range(1, nodes+1)}
    save(STATE/'inventory.json', {'all': {'children': {'cpnginx': {'hosts': hosts, 'vars': {
        'ansible_user': 'lab', 'ansible_python_interpreter': '/usr/bin/python3',
        'ansible_ssh_private_key_file': str(STATE/'ssh/id_ed25519'),
        'ansible_ssh_common_args': '-o StrictHostKeyChecking=yes -o UserKnownHostsFile='+str(STATE/'ssh/known_hosts'),
        'cpnginx_configure_vault_addr': VAULT_URL,
        'cpnginx_configure_vault_role_id': app['role_id'],
        'cpnginx_configure_vault_secret_id': app['secret_id'],
    }}}}})


def up(nodes):
    require_prepared()
    license_path = STATE/'server.license'
    if not license_path.is_file() or not license_path.read_text().strip():
        raise LabError('Provide your appropriate TLS Server license first: prepare --license-file /private/path/tls-server.license. Ordinary Demo CSP did not support server TLS in this image')
    if nodes == 1:
        compose('rm', '-s', '-f', 'proxy02', two=True, check=False, capture=True)
    services = ['vault', 'partner', 'proxy01'] + (['proxy02'] if nodes == 2 else [])
    started = time.monotonic()
    compose('up', '-d', '--wait', '--wait-timeout', '120', '--no-build', '--pull', 'never', *services, two=nodes == 2)
    bootstrap_vault()
    keys = []
    for i in range(1, nodes+1):
        scan = run(['ssh-keyscan', '-T', '5', '-p', str(2220+i), '127.0.0.1'], capture=True)
        if not scan.stdout.strip():
            raise LabError('SSH host keys could not be obtained from the local demo ports')
        keys.append(scan.stdout)
    (STATE/'ssh/known_hosts').write_text(''.join(keys))
    inventory(nodes)
    save(STATE/'run.json', {'nodes': nodes})
    print(f'Ready: {nodes} gateway(s), startup {time.monotonic()-started:.1f}s')
    print('Vault: http://localhost:18200 (lab.sh token prints the local demo root token)')
    print('Direct TLS: https://cpnginx.example.test:15100/tls')
    print('Direct mTLS: https://cpnginx.example.test:15101/mtls')
    print('Proxy: http://localhost:18080/mtls'+(' and http://localhost:18081/mtls' if nodes == 2 else ''))


def source_snapshot(cached):
    cache = STATE/'git-cache'
    ref = os.environ.get('LAB_CONFIG_REF', 'main')
    if not (cache/'.git').exists():
        if cached:
            raise LabError('There is no cached GitHub checkout')
        run(['git', 'clone', '--branch', ref, '--depth', '1', GIT_URL, cache])
    elif not cached:
        run(['git', '-C', cache, 'fetch', 'origin', ref])
        run(['git', '-C', cache, 'reset', '--hard', 'FETCH_HEAD'])
    sha = run(['git', '-C', cache, 'rev-parse', 'HEAD'], capture=True).stdout.strip()
    current = STATE/'current-configs'
    if current.exists():
        shutil.rmtree(current)
    current.mkdir()
    # Export only committed files. Untracked files in the Git cache never become input.
    data = subprocess.run(['git', '-C', str(cache), 'archive', 'HEAD'], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(current, filter='data')
    print(('CACHED ' if cached else 'GitHub ')+'commit: '+sha, flush=True)
    return current/'integrations/demo'


def configure(args):
    require_prepared()
    if not (STATE/'run.json').exists():
        raise LabError('Start the lab first')
    # Refresh machine credentials, including after a long pause before the presentation.
    bootstrap_vault()
    inventory(load(STATE/'run.json')['nodes'])
    directory = Path(args.configs_dir).resolve() if args.configs_dir else source_snapshot(args.cached)
    if not directory.is_dir():
        raise LabError('The integration directory is missing. Publish the new format under integrations/demo or use --configs-dir explicitly')
    if args.configs_dir:
        print('Explicit local integration source: '+str(directory), flush=True)
    variables = {
        'cpnginx_configure_git_clone_enabled': False,
        'cpnginx_configure_gitlab_configs_dir': str(directory),
        'cpnginx_configure_gitlab_ca_certs_dir': str(STATE/'assets/ca'),
        'cpnginx_configure_gitlab_subca_certs_dir': str(STATE/'assets/subca'),
        'cpnginx_configure_default_conf': str(LAB/'files/default.conf'),
        'cpnginx_configure_cpnginx_conf': str(LAB/'files/cpnginx.conf'),
    }
    (STATE/'assets/subca').mkdir(exist_ok=True)
    save(STATE/'playbook.json', [{'name': 'Configure portable GOST gateways', 'hosts': 'cpnginx', 'become': True, 'vars': variables, 'roles': ['cryptogates.cpnginx_configure']}])
    env = os.environ.copy()
    env['ANSIBLE_CONFIG'] = str(STATE/'ansible.cfg')
    env['ANSIBLE_LOCAL_TEMP'] = str(STATE/'ansible-tmp')
    env['PATH'] = str(STATE/'bin')+':'+str(STATE/'venv/bin')+':'+env['PATH']
    run([STATE/'venv/bin/ansible-playbook', '-i', STATE/'inventory.json', STATE/'playbook.json'], env=env)


def probe(port):
    return compose('exec', '-T', '--user', 'lab', 'proxy01', '/opt/cprocsp/bin/amd64/csptest', '-tlsc',
                   '-server', 'cpnginx.example.test', '-port', str(port), '-file', '/tls' if port == 5100 else '/mtls',
                   '-proto', '6', '-exchange', '3', '-autocheck', '-nosave', '-silent', capture=True, check=False)


def partner_log(name):
    if name not in ('access', 'error'):
        raise LabError('Unsupported log')
    return compose('exec', '-T', 'partner', 'cat', '/var/log/cpnginx/'+name+'.log', capture=True).stdout


def log_delta(before, after):
    if not after.startswith(before):
        raise LabError('Partner log changed during the check; repeat the check')
    return after[len(before):]


def check(stage):
    require_prepared()
    nodes = load(STATE/'run.json')['nodes']
    access_before = partner_log('access')
    control = probe(5100)
    control_access = log_delta(access_before, partner_log('access'))
    if control.returncode or 'status=200' not in control_access or '/tls' not in control_access:
        raise LabError('The GOST TLS control failed; this is not evidence of an mTLS certificate requirement. Inspect partner trust and TLS Server license')
    error_before = partner_log('error')
    negative = probe(5101)
    negative_errors = log_delta(error_before, partner_log('error'))
    if 'Доступ через ГОСТ mTLS' in negative.stdout or 'client sent no required SSL certificate' not in negative_errors:
        raise LabError('No confirmed rejection for a missing client certificate. A timeout or another TLS error is not a successful negative test')
    print('PASS: GOST TLS control; direct mTLS without a client key is rejected')
    successes = 0
    for i in range(nodes):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{18080+i}/mtls', timeout=15) as response:
                body = response.read().decode()
                ok = response.status == 200 and 'Доступ через ГОСТ mTLS' in body
        except (urllib.error.URLError, OSError):
            ok = False
        successes += int(ok)
        if stage == 'after' and not ok:
            raise LabError(f'proxy{i+1:02d}: protected page is not available')
        if stage == 'before' and ok:
            raise LabError('The gateway is already configured; run reset-demo before the initial demonstration')
        print(f'proxy{i+1:02d}: '+('protected page is available' if ok else 'not configured / unavailable'))
    print(f'Check complete: {successes}/{nodes} proxies serve the protected page')


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '_vault':
        token = os.environ.get('VAULT_TOKEN', '')
        sys.exit(compose('exec', '-T', '-e', 'VAULT_ADDR=http://127.0.0.1:8200', '-e', 'VAULT_TOKEN='+token, 'vault', 'vault', *sys.argv[2:], check=False).returncode)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--archive')
    p.add_argument('--license-file', help='Private file with your appropriate CryptoPro TLS Server license')
    p.add_argument('--local-roles', action='store_true', help='Development: copy sibling role working trees instead of fetching GitHub')
    p.add_argument('--renew-certs', action='store_true')
    p = sub.add_parser('up'); p.add_argument('--nodes', type=int, choices=[1, 2], default=1)
    p = sub.add_parser('configure'); p.add_argument('--cached', action='store_true'); p.add_argument('--configs-dir')
    p = sub.add_parser('check'); p.add_argument('--stage', choices=['before', 'after', 'auto'], default='auto')
    for name in ['reset-demo', 'down', 'status', 'token']:
        sub.add_parser(name)
    args = parser.parse_args()
    if args.command == 'prepare': prepare(args)
    elif args.command == 'up': up(args.nodes)
    elif args.command == 'configure': configure(args)
    elif args.command == 'check': check(args.stage)
    elif args.command == 'down': compose('down', two=True)
    elif args.command == 'status': compose('ps', '-a', two=True)
    elif args.command == 'token': print(root_token())
    elif args.command == 'reset-demo':
        nodes = load(STATE/'run.json')['nodes']
        bootstrap_vault()
        try:
            api('cpnginx/metadata/demo/client', method='DELETE', token=root_token())
        except LabError as exc:
            if 'HTTP 404' not in str(exc): raise
        compose('rm', '-s', '-f', 'proxy01', 'proxy02', two=True)
        up(nodes)
        print('Demo key and gateway state reset. Source PFX, GitHub and partner certificate are unchanged.')


if __name__ == '__main__':
    try:
        main()
    except (LabError, FileNotFoundError, subprocess.SubprocessError) as exc:
        print('ERROR: '+str(exc), file=sys.stderr)
        sys.exit(1)
