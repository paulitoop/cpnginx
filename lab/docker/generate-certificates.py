"""Generate a private GOST MiniCA and export only demo leaf PFX files."""
from pathlib import Path
import json
import atexit
import re
import secrets
import subprocess
import os

assets = Path('/assets')
assets.mkdir(exist_ok=True)

def owner_cleanup():
    if 'LAB_OWNER_UID' not in os.environ:
        return
    uid, gid = int(os.environ['LAB_OWNER_UID']), int(os.environ['LAB_OWNER_GID'])
    for path in [*assets.rglob('*'), assets]:
        os.chown(path, uid, gid)
    if (assets/'ca').exists():
        (assets/'ca').chmod(0o755)

atexit.register(owner_cleanup)
os.umask(0o077)
pins = {name: secrets.token_hex(24) for name in ['server', 'client']}
csptest = '/opt/cprocsp/bin/amd64/csptest'
certmgr = '/opt/cprocsp/bin/amd64/certmgr'

def run(args):
    # Only the isolated generator accepts its own MiniCA root confirmation.
    answer = 'o\n' if '-root' in args else (args[args.index('-pin')+1]+'\n' if '-export' in args else '')
    result = subprocess.run(args, input=answer, capture_output=True, text=True, timeout=30)
    if result.returncode:
        output = (result.stdout+result.stderr)[-3000:]
        for secret in [ca_pin, *pins.values()]:
            output = output.replace(secret, '[REDACTED]')
        raise RuntimeError(output)
    return result.stdout

root_dn = 'CN=CPNGINX Lab Root'
subprocess.run(['python3', '/usr/local/bin/init-rng.py'], check=True)
ca_pin = secrets.token_hex(24)
run([csptest, '-minica', '-root', '-dn', root_dn, '-provtype', '80',
     '-container', 'lab-ca', '-password', ca_pin, '-keytype', 'exchange', '-until', '730',
     '-fcert', str(assets/'root.cer')])
for name, usage in [('server', '1.3.6.1.5.5.7.3.1'), ('client', '1.3.6.1.5.5.7.3.2')]:
    dn = 'CN=cpnginx.example.test' if name == 'server' else 'CN=CPNGINX Lab Client'
    args = [csptest, '-minica', '-leaf', '-dn', dn, '-provtype', '80',
            '-container', 'lab-'+name, '-password', pins[name], '-exportable',
            '-keytype', 'exchange', '-certusage', usage, '-until', '365',
            '-issuer', root_dn, '-ipassword', ca_pin, '-fcert', str(assets/(name+'.cer'))]
    if name == 'server':
        args += ['-altname', 'cpnginx.example.test']
    run(args)
    run([certmgr, '-export', '-pfx', '-dn', dn, '-dest', str(assets/(name+'.pfx')), '-pin', pins[name]])
run([csptest, '-minica', '-crl', '-issuer', root_dn, '-ipassword', ca_pin, '-until', '180',
     '-fcrl', str(assets/'root.crl')])
(assets/'pins.json').write_text(json.dumps(pins))
(assets/'server.pin').write_text(pins['server'])
(assets/'ca').mkdir(exist_ok=True)
for name in ['root.cer','root.crl']:
    (assets/'ca'/name).write_bytes((assets/name).read_bytes())
# Leaf files and trust material must be readable by the service user in the partner.
for path in [assets/'server.pfx', assets/'server.pin', *list((assets/'ca').iterdir())]:
    path.chmod(0o644)
print('Created GOST MiniCA, server/client certificates, PFX and CRL. Private files stay local.')
