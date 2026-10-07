#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/audit_dependencies.sh [--json-output FILE] [pip-audit options...]

Audits the locked production dependencies with pip-audit and prints the result
in the console. With --json-output, the report is also exported as JSON to FILE.
Any other argument is passed through to pip-audit.
EOF
}

json_output=""
pip_audit_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --json-output)
      if [[ $# -lt 2 ]]; then
        echo "error: --json-output requires a file path" >&2
        exit 2
      fi
      json_output="$2"
      shift 2
      ;;
    --json-output=*)
      json_output="${1#*=}"
      shift
      ;;
    *)
      pip_audit_args+=("$1")
      shift
      ;;
  esac
done

audit_requirements="$(mktemp)"
trap 'rm -f "$audit_requirements"' EXIT

# Fail clearly if pyproject.toml and uv.lock disagree.
uv lock --check

# Audit the exact locked production dependencies.
uv export \
  --quiet \
  --locked \
  --no-dev \
  --no-emit-project \
  --format requirements.txt \
  --output-file "$audit_requirements"

run_pip_audit() {
  uv run --locked --extra test pip-audit \
    --requirement "$audit_requirements" \
    --no-deps \
    --disable-pip \
    ${pip_audit_args[@]+"${pip_audit_args[@]}"} \
    "$@"
}

# pip-audit emits a single format per run, so the JSON export and the console
# report are two runs. Both run even if the first finds vulnerabilities, and
# the script fails if either does.
status=0

if [[ -n "$json_output" ]]; then
  mkdir -p "$(dirname "$json_output")"
  run_pip_audit --format json --output "$json_output" || status=$?
  echo "JSON report written to $json_output" >&2
fi

run_pip_audit || status=$?

exit "$status"
