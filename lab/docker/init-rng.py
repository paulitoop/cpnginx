"""Fresh OS-CSPRNG input for CPSD, ONLY for this disposable demonstration.

CPSD records are 32 data bytes + a little-endian CRC32 (36 bytes), as verified
against genkpim from the installed CSP. Never use a fixed/shared test gamma.
This bypasses certified entropy collection and is not a production procedure.
The vendor describes the record layout in its external-gamma workstation guide.
"""
from pathlib import Path
import os
import grp
import struct
import subprocess
import zlib


def fresh_pool(count=1024):
    records = []
    for _ in range(count):
        sample = os.urandom(32)
        records.append(sample + struct.pack('<I', zlib.crc32(sample)))
    return b''.join(records)


def main():
    directory = Path('/var/opt/cprocsp/dsrf')
    # New pool on every container start. It is never part of a Docker image.
    pool = fresh_pool()
    for name in ['db1', 'db2']:
        path = directory/name/'kis_1'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pool)
        os.chown(path, 0, grp.getgrnam('lab-rng').gr_gid)
        path.chmod(0o660)  # Only the lab service group can consume portions.
    subprocess.run(['/opt/cprocsp/sbin/amd64/cpconfig', '-hardware', 'rndm', '-del', 'BIO_TUI'],
                   check=True, stdout=subprocess.DEVNULL)
    print('Initialized fresh per-start laboratory CPSD from OS CSPRNG', flush=True)


if __name__ == '__main__':
    main()
