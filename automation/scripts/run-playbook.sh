#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

ANSIBLE_PLAYBOOK="${ANSIBLE_PLAYBOOK:-ansible-playbook}"
INVENTORY="${INVENTORY:-$REPO_DIR/inventory/hosts.yml}"
PLAYBOOK="${1:-configure}"
NIR_LAB_BIN="${NIR_LAB_BIN:-$REPO_DIR/../lab/vault/bin}"

if [[ -d "$NIR_LAB_BIN" ]]; then
  export PATH="$NIR_LAB_BIN:$PATH"
fi

case "$PLAYBOOK" in
  configure|cpnginx_configure)
    PLAYBOOK_PATH="$REPO_DIR/playbooks/cpnginx_configure.yaml"
    shift || true
    ;;
  install|cpnginx_install)
    PLAYBOOK_PATH="$REPO_DIR/playbooks/cpnginx_install.yaml"
    shift || true
    ;;
  site|all)
    PLAYBOOK_PATH="$REPO_DIR/playbooks/site.yml"
    shift || true
    ;;
  *.yml|*.yaml)
    PLAYBOOK_PATH="$PLAYBOOK"
    shift || true
    ;;
  -h|--help)
    cat <<EOF
Usage:
  $0 [configure|install|site|PLAYBOOK_PATH] [ansible-playbook args...]

Examples:
  $0
  $0 configure --tags lab_hosts
  $0 install --limit cpnginx-proxy01
  $0 site --check

Environment:
  ANSIBLE_PLAYBOOK=$ANSIBLE_PLAYBOOK
  INVENTORY=$INVENTORY
  NIR_LAB_BIN=$NIR_LAB_BIN
EOF
    exit 0
    ;;
  *)
    echo "Unknown playbook alias: $PLAYBOOK" >&2
    echo "Run '$0 --help' for usage." >&2
    exit 2
    ;;
esac

if ! command -v "$ANSIBLE_PLAYBOOK" >/dev/null 2>&1; then
  echo "ansible-playbook is not executable: $ANSIBLE_PLAYBOOK" >&2
  echo "Set ANSIBLE_PLAYBOOK=/path/to/ansible-playbook if needed." >&2
  exit 1
fi

cd "$REPO_DIR"
export ANSIBLE_CONFIG="${ANSIBLE_CONFIG:-$REPO_DIR/ansible.cfg}"
exec "$ANSIBLE_PLAYBOOK" -i "$INVENTORY" "$PLAYBOOK_PATH" "$@"
