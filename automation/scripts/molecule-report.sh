#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="${ROLE_REPOSITORIES_DIR:-$(cd "$ROOT_DIR/../.." && pwd)}"
VENV_BIN="${VENV_BIN:-$ROOT_DIR/.venv/bin}"
MOLECULE="${MOLECULE:-$VENV_BIN/molecule}"
MOLECULE_TEST_ARGS="${MOLECULE_TEST_ARGS:---command-borders --report}"
REPORT_ROOT="${REPORT_ROOT:-$ROOT_DIR/reports/molecule}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
REPORT_DIR="$REPORT_ROOT/$TIMESTAMP"

export PATH="$VENV_BIN:$PATH"

roles=(
  "ansible-role-cpnginx_install"
  "ansible-role-cpnginx_configure"
)

mkdir -p "$REPORT_DIR"

summary="$REPORT_DIR/summary.md"

prepare_molecule_roles() {
  local configure_roles_dir="$WORK_DIR/ansible-role-cpnginx_configure/molecule/default/roles"

  mkdir -p "$configure_roles_dir"
  ln -sfn "$WORK_DIR/ansible-role-cpnginx_configure" \
    "$configure_roles_dir/cryptogates.cpnginx_configure"
  ln -sfn "$WORK_DIR/ansible-role-cpnginx_install" \
    "$configure_roles_dir/cryptogates.cpnginx_install"
}

prepare_molecule_roles

cat > "$summary" <<EOF
# Molecule report

Date: $(date --iso-8601=seconds)

| Role | Command | Result | Log |
| --- | --- | --- | --- |
EOF

run_role() {
  local role="$1"
  local role_dir="$WORK_DIR/$role"
  local log="$REPORT_DIR/${role}.log"
  local status="PASS"

  echo "==> Running Molecule for $role"
  (
    cd "$role_dir"
    # shellcheck disable=SC2086
    "$MOLECULE" test $MOLECULE_TEST_ARGS
  ) 2>&1 | tee "$log" || status="FAIL"

  printf '| `%s` | `%s` | `%s` | `%s` |\n' \
    "$role" \
    "molecule test $MOLECULE_TEST_ARGS" \
    "$status" \
    "$(basename "$log")" >> "$summary"

  {
    echo
    echo "## $role"
    echo
    echo '```text'
    grep -E "PLAY RECAP|failed=|changed=|idempotence|Verifier completed|ERROR|FAILED" "$log" || true
    echo '```'
  } >> "$summary"

  [[ "$status" == "PASS" ]]
}

overall_status=0
for role in "${roles[@]}"; do
  run_role "$role" || overall_status=1
done

cat >> "$summary" <<EOF

## Useful commands for the report

\`\`\`bash
cd /opt/work/ansible/ansible-role-cpnginx_install
molecule test --command-borders --report

cd /opt/work/ansible/ansible-role-cpnginx_configure
molecule test --command-borders --report
\`\`\`

## Stored artifacts

\`\`\`text
$REPORT_DIR
\`\`\`
EOF

echo
echo "Report directory: $REPORT_DIR"
echo "Summary: $summary"

exit "$overall_status"
