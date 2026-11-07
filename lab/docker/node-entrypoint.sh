#!/usr/bin/env bash
set -euo pipefail
python3 /usr/local/bin/init-rng.py
mkdir -p /run/sshd /home/lab/.ssh /var/log/cpnginx
ssh-keygen -A >/dev/null 2>&1
install -o lab -g lab -m 0600 /run/lab/authorized_keys /home/lab/.ssh/authorized_keys
printf '%s\n' 'PasswordAuthentication no' 'PermitRootLogin no' 'AllowUsers lab' > /etc/ssh/sshd_config.d/lab.conf
for f in /run/lab/ca/*.cer; do
    printf 'o\n' | sudo -u lab /opt/cprocsp/bin/amd64/certmgr -install -store uRoot -file "$f" >/dev/null
done
for f in /run/lab/ca/*.crl; do
    sudo -u lab /opt/cprocsp/bin/amd64/certmgr -install -crl -store uCA -file "$f" >/dev/null
done
/opt/cprocsp/sbin/amd64/cpnginx -t
/opt/cprocsp/sbin/amd64/cpnginx
exec /usr/sbin/sshd -D -e
