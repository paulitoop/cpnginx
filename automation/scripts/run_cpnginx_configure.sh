#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 HOST_OR_GROUP [ansible-playbook arguments...]" >&2
  exit 2
fi
TARGET_HOSTS="$1"
shift
exec "$SCRIPT_DIR/run-playbook.sh" configure --limit "$TARGET_HOSTS" "$@"
