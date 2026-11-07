FROM ubuntu:24.04

ARG ROLE=server

COPY ./dist/linux-amd64_deb.tgz /tmp/linux-amd64_deb.tgz

RUN tar -xvzf /tmp/linux-amd64_deb.tgz -C /tmp --strip-components 1 \
    && /tmp/install.sh --yes kc1 cprocsp-nginx \
    && :

RUN rm -f /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources && \
    printf '%s\n' \
    'Types: deb' \
    'URIs: http://archive.ubuntu.com/ubuntu' \
    'Suites: noble noble-updates noble-backports' \
    'Components: main universe restricted multiverse' \
    'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg' \
    '' \
    'Types: deb' \
    'URIs: http://security.ubuntu.com/ubuntu' \
    'Suites: noble-security' \
    'Components: main universe restricted multiverse' \
    'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg' \
    > /etc/apt/sources.list.d/ubuntu.sources && \
    echo 'Acquire::Languages "none";' > /etc/apt/apt.conf.d/99no-translations && \
    echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4 && \
    apt-get update

RUN apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    telnet iproute2 dnsutils nano \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /etc/opt/cprocsp/cpnginx/conf.d \
    && mkdir -p /var/run/cpnginx \
    && mkdir -p /app \
    && chown -R cpnginx:cpnginx /var/run/cpnginx \
    && chown -R cpnginx:cpnginx /etc/opt/cprocsp/cpnginx \
    && chown -R cpnginx:cpnginx /app \
    && chown -R cpnginx:cpnginx /var/opt/cprocsp/cpnginx

COPY ./${ROLE}/configs/cpnginx.conf /etc/opt/cprocsp/cpnginx/cpnginx.conf
COPY ./${ROLE}/configs/default.conf /app/templates/default.conf.template

COPY ./${ROLE}/requirements.txt /tmp/requirements.txt

RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

COPY ./common /app/common
COPY ./${ROLE}/cpnginx /app/cpnginx
COPY ./${ROLE}/certs/ca /app/certs/ca
COPY ./${ROLE}/configs/mtls.conf.template /app/templates/mtls.conf.template

RUN chown -R cpnginx:cpnginx /app

WORKDIR /app

ENV PATH="/opt/cprocsp/bin/amd64:/opt/cprocsp/sbin/amd64:/opt/venv/bin:${PATH}"
ENV PYTHONPATH="/app:${PYTHONPATH}"

ENV CSP_LICENSE="" \
    CONTAINER_ZIP_BASE64="" \
    SERVER_PRIVATE_KEY_PASSWORD="" \
    CONTAINER_TAR_BASE64="" \
    LOG_LEVEL="INFO" \
    ENV="unknown" \
    SYSTEM_JSON_LOG="gost-proxy"

EXPOSE 8080

USER cpnginx

ENTRYPOINT ["python", "-m", "cpnginx"]
