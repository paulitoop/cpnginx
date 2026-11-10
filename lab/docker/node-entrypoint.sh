#!/usr/bin/env bash
set -euo pipefail
mkdir -p /run/sshd /home/lab/.ssh
ssh-keygen -A >/dev/null 2>&1
install -o lab -g lab -m 0600 /run/lab/authorized_keys /home/lab/.ssh/authorized_keys
printf '%s\n' 'PasswordAuthentication no' 'PermitRootLogin no' 'AllowUsers lab' > /etc/ssh/sshd_config.d/lab.conf
if [[ -x /opt/cprocsp/sbin/amd64/cpnginx ]]; then
    python3 /usr/local/bin/init-rng.py
    /opt/cprocsp/sbin/amd64/cpnginx -t
    /opt/cprocsp/sbin/amd64/cpnginx
fi
exec /usr/sbin/sshd -D -e
