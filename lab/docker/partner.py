"""Import only the partner's server key and start the strict test endpoints."""
import json
from pathlib import Path
import re
import subprocess
import os
from jinja2 import Template

def run(args):
    result = subprocess.run(args, input='o\n' if 'uRoot' in args else '', capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('CryptoPro initialization failed: '+(result.stdout+result.stderr)[-2000:].replace(pin, '[REDACTED]'))
    return result.stdout

certmgr = "/opt/cprocsp/bin/amd64/certmgr"
subprocess.run(['python3', '/usr/local/bin/init-rng.py'], check=True)
license_path = Path('/run/lab/server.license')
license_value = license_path.read_text().strip() if license_path.is_file() else ''
if license_value:
    result = subprocess.run(['/opt/cprocsp/sbin/amd64/cpconfig', '-license', '-set', license_value],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('The supplied CryptoPro TLS server license was not accepted; value is hidden')
else:
    print('No TLS Server license supplied. Demo CSP may reject server handshakes. See prepare --license-file.', flush=True)

pin = Path('/run/lab/server.pin').read_text().strip()
prefix = ['sudo', '-u', 'cpnginx', certmgr]
for cert in sorted(Path('/run/lab/ca').glob('*.cer')):
    run(prefix + ['-install', '-store', 'uRoot', '-file', str(cert)])
for crl in sorted(Path('/run/lab/ca').glob('*.crl')):
    run(prefix + ['-install', '-crl', '-store', 'uCA', '-file', str(crl)])
run(prefix + ['-install', '-pfx', '-file', '/run/lab/server.pfx', '-pin', pin, '-newpin', ''])
listing = run(prefix + ['-list', '-store', 'uMy'])
serials = re.findall(r'(?:Serial(?: Number)?|Серийный номер)\s*:\s*(0x[0-9a-fA-F]+)', listing)
if len(serials) != 1:
    raise RuntimeError('Expected exactly one server certificate in the partner store')
template = Template(Path('/opt/lab/partner.conf.j2').read_text())
Path('/etc/opt/cprocsp/cpnginx/conf.d/partner.conf').write_text(template.render(serial=serials[0]))
subprocess.run(['/opt/cprocsp/sbin/amd64/cpnginx', '-t'], check=True)
os.execv('/opt/cprocsp/sbin/amd64/cpnginx', ['cpnginx', '-g', 'daemon off;'])
