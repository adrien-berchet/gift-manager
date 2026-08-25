#!/usr/bin/env bash
set -euo pipefail

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

uv run --locked --extra test pip-audit \
  --requirement "$audit_requirements" \
  --no-deps \
  --disable-pip \
  "$@"
