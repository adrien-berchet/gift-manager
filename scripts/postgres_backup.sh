#!/usr/bin/env bash
set -euo pipefail

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${BACKUP_DIR:?BACKUP_DIR is required}"
BACKUP_REASON="${BACKUP_REASON:-scheduled}"
DB_MODE="${BACKUP_DB_MODE:-direct}"
DB_NAME="${DB_NAME:?DB_NAME is required}"
DB_USER="${DB_USER:?DB_USER is required}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

mkdir -p "${BACKUP_DIR}"

tmp_dir="$(mktemp -d)"
dump_path="${tmp_dir}/${DB_NAME}-${TIMESTAMP}.dump"
manifest_path="${BACKUP_DIR}/${DB_NAME}-${TIMESTAMP}.manifest"

notify() {
    local url="${1:-}"
    if [[ -n "${url}" ]]; then
        curl -fsS --max-time 10 --output /dev/null "${url}" || true
    fi
}

on_exit() {
    local status=$?
    rm -rf "${tmp_dir}"
    if [[ ${status} -ne 0 ]]; then
        notify "${BACKUP_MONITOR_FAILURE_URL:-}"
    fi
    return "${status}"
}
trap on_exit EXIT

encrypt_backup() {
    local source_path=$1
    local encrypted_path

    if [[ -n "${BACKUP_AGE_RECIPIENT:-}" ]]; then
        command -v age >/dev/null
        encrypted_path="${BACKUP_DIR}/${DB_NAME}-${TIMESTAMP}.dump.age"
        age -r "${BACKUP_AGE_RECIPIENT}" -o "${encrypted_path}" "${source_path}"
    elif [[ -n "${BACKUP_GPG_RECIPIENT:-}" ]]; then
        command -v gpg >/dev/null
        encrypted_path="${BACKUP_DIR}/${DB_NAME}-${TIMESTAMP}.dump.gpg"
        gpg --batch --yes --encrypt --recipient "${BACKUP_GPG_RECIPIENT}" \
            --output "${encrypted_path}" "${source_path}"
    elif [[ -n "${BACKUP_PASSPHRASE:-}" ]]; then
        command -v gpg >/dev/null
        encrypted_path="${BACKUP_DIR}/${DB_NAME}-${TIMESTAMP}.dump.gpg"
        printf '%s' "${BACKUP_PASSPHRASE}" | gpg --batch --yes --pinentry-mode loopback \
            --passphrase-fd 0 --symmetric --cipher-algo AES256 \
            --output "${encrypted_path}" "${source_path}"
    else
        echo "Set BACKUP_AGE_RECIPIENT, BACKUP_GPG_RECIPIENT, or BACKUP_PASSPHRASE." >&2
        return 1
    fi

    printf '%s\n' "${encrypted_path}"
}

if [[ "${DB_MODE}" == "compose" ]]; then
    docker compose exec -T db pg_dump -U "${DB_USER}" -d "${DB_NAME}" \
        --format=custom --no-owner --no-acl --verbose > "${dump_path}"
else
    PGPASSWORD="${DB_PASSWORD:?DB_PASSWORD is required}" pg_dump \
        -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
        --format=custom --no-owner --no-acl --verbose --file="${dump_path}"
fi

encrypted_backup="$(encrypt_backup "${dump_path}")"
(
    cd "$(dirname "${encrypted_backup}")"
    sha256sum "$(basename "${encrypted_backup}")" > "$(basename "${encrypted_backup}").sha256"
)

{
    printf 'created_at=%s\n' "${TIMESTAMP}"
    printf 'reason=%s\n' "${BACKUP_REASON}"
    printf 'database=%s\n' "${DB_NAME}"
    printf 'db_host=%s\n' "${DB_HOST}"
    printf 'db_mode=%s\n' "${DB_MODE}"
    printf 'git_sha=%s\n' "$(git rev-parse HEAD 2>/dev/null || printf 'unknown')"
    printf 'backup_file=%s\n' "${encrypted_backup}"
    printf 'backup_sha256=%s\n' "$(cut -d ' ' -f 1 "${encrypted_backup}.sha256")"
    printf 'backup_bytes=%s\n' "$(wc -c < "${encrypted_backup}")"
} > "${manifest_path}"

if [[ -n "${BACKUP_UPLOAD_CMD:-}" ]]; then
    BACKUP_FILE="${encrypted_backup}" BACKUP_MANIFEST="${manifest_path}" sh -c "${BACKUP_UPLOAD_CMD}"
fi

cp "${manifest_path}" "${BACKUP_DIR}/latest-postgres.manifest"
notify "${BACKUP_MONITOR_SUCCESS_URL:-}"
printf 'Created encrypted PostgreSQL backup: %s\n' "${encrypted_backup}"
