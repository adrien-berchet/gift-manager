#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:?BACKUP_DIR is required}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PLAN_PATH="${BACKUP_DIR}/pre-migration-plan-${TIMESTAMP}.txt"

mkdir -p "${BACKUP_DIR}"

BACKUP_REASON="${BACKUP_REASON:-pre-migration}" "${SCRIPT_DIR}/postgres_backup.sh"

if [[ "${MEDIA_BACKUP_ENABLED:-false}" == "true" ]]; then
    "${SCRIPT_DIR}/media_backup.sh"
fi

if [[ -f manage.py ]] && command -v python >/dev/null; then
    python manage.py showmigrations --plan > "${PLAN_PATH}"
    printf 'Saved migration plan: %s\n' "${PLAN_PATH}"
fi
