FROM ubuntu:24.04 AS gateway
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server sudo python3 python3-jinja2 ca-certificates openssl \
    curl procps iproute2 net-tools unzip \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -s /bin/bash lab \
    && groupadd -r lab-rng \
    && usermod -aG lab-rng lab \
    && printf 'lab ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/lab \
    && chmod 0440 /etc/sudoers.d/lab \
    && rm -f /etc/ssh/ssh_host_* \
    && mkdir -p /run/sshd /home/lab/.ssh \
    && chmod 0700 /home/lab/.ssh \
    && chown -R lab:lab /home/lab/.ssh
COPY --chmod=0755 docker/node-entrypoint.sh /usr/local/bin/node-entrypoint
COPY docker/init-rng.py /usr/local/bin/init-rng.py
EXPOSE 22 30443
ENTRYPOINT ["/usr/local/bin/node-entrypoint"]

FROM gateway AS partner
COPY dist/linux-amd64_deb.tgz /tmp/csp.tgz
RUN mkdir /tmp/csp && tar -xzf /tmp/csp.tgz -C /tmp/csp --strip-components=1 \
    && cd /tmp/csp && ./install.sh --yes kc1 cprocsp-nginx \
    && rm -rf /tmp/csp /tmp/csp.tgz \
    && usermod -aG lab-rng cpnginx \
    && mkdir -p /var/log/cpnginx /etc/opt/cprocsp/cpnginx/conf.d/portals
ENV PATH="/opt/cprocsp/bin/amd64:/opt/cprocsp/sbin/amd64:${PATH}"
COPY docker/partner.py /usr/local/bin/lab-partner.py
COPY docker/lab_license.py /usr/local/bin/lab_license.py
COPY docker/generate-certificates.py /usr/local/bin/generate-certificates.py
COPY files/cpnginx.conf /etc/opt/cprocsp/cpnginx/cpnginx.conf
COPY files/default.conf /etc/opt/cprocsp/cpnginx/conf.d/default.conf
COPY files/partner.conf.j2 /opt/lab/partner.conf.j2
EXPOSE 5100 5101
ENTRYPOINT ["python3", "/usr/local/bin/lab-partner.py"]
