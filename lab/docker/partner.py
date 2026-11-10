"""Import only the partner's server key and start the strict test endpoints."""
from pathlib import Path
import json
import re
import subprocess
import os
from urllib.request import Request, urlopen
from jinja2 import Template
from lab_license import install_license


def vault_license():
    credentials = json.loads(Path('/run/lab-vault/approle.json').read_text())
    url = 'http://vault:8200/v1/'
    login = Request(url+'auth/approle/login', json.dumps(credentials).encode(),
                    {'Content-Type': 'application/json'})
    try:
        with urlopen(login, timeout=10) as response:
            token = json.load(response)['auth']['client_token']
        secret = Request(url+'cpnginx/data/licenses/partner', headers={'X-Vault-Token': token})
        with urlopen(secret, timeout=10) as response:
            return json.load(response)['data']['data']['license']
    except (OSError, KeyError, ValueError):
        raise RuntimeError('Cannot obtain the partner license from Vault; run lab.sh up') from None

def run(args):
    result = subprocess.run(args, input='o\n' if 'uRoot' in args else '', capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('CryptoPro initialization failed: '+(result.stdout+result.stderr)[-2000:].replace(pin, '[REDACTED]'))
    return result.stdout

certmgr = "/opt/cprocsp/bin/amd64/certmgr"
subprocess.run(['python3', '/usr/local/bin/init-rng.py'], check=True)
install_license(vault_license())

pin = Path('/run/lab/server.pin').read_text().strip()
prefix = ['sudo', '-u', 'cpnginx', certmgr]
for user in ['lab', 'cpnginx']:
    for cert in sorted(Path('/run/lab/ca').glob('*.cer')):
        run(['sudo', '-u', user, certmgr, '-install', '-store', 'uRoot', '-file', str(cert)])
    for crl in sorted(Path('/run/lab/ca').glob('*.crl')):
        run(['sudo', '-u', user, certmgr, '-install', '-crl', '-store', 'uCA', '-file', str(crl)])
run(prefix + ['-install', '-pfx', '-file', '/run/lab/server.pfx', '-pin', pin, '-newpin', ''])
listing = run(prefix + ['-list', '-store', 'uMy'])
serials = re.findall(r'(?:Serial(?: Number)?|Серийный номер)\s*:\s*(0x[0-9a-fA-F]+)', listing)
if len(serials) != 1:
    raise RuntimeError('Expected exactly one server certificate in the partner store')
template = Template(Path('/opt/lab/partner.conf.j2').read_text())
Path('/etc/opt/cprocsp/cpnginx/conf.d/partner.conf').write_text(template.render(serial=serials[0]))
subprocess.run(['/opt/cprocsp/sbin/amd64/cpnginx', '-t'], check=True)
os.execv('/opt/cprocsp/sbin/amd64/cpnginx', ['cpnginx', '-g', 'daemon off;'])
