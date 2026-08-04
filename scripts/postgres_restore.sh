#!/usr/bin/env bash
set -euo pipefail

BACKUP_FILE="${BACKUP_FILE:?BACKUP_FILE is required}"
DB_MODE="${BACKUP_DB_MODE:-direct}"
DB_NAME="${DB_NAME:?DB_NAME is required}"
DB_USER="${DB_USER:?DB_USER is required}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

if [[ "${ALLOW_DESTRUCTIVE_RESTORE:-}" != "yes" ]]; then
    echo "Set ALLOW_DESTRUCTIVE_RESTORE=yes to restore into ${DB_NAME}." >&2
    exit 1
fi

tmp_dir="$(mktemp -d)"
restore_path="${tmp_dir}/restore.dump"

verify_checksum() {
    local candidate=$1
    if [[ -f "${candidate}.sha256" ]]; then
        (
            cd "$(dirname "${candidate}")"
            sha256sum --check "$(basename "${candidate}").sha256"
        )
    fi
}

cleanup() {
    rm -rf "${tmp_dir}"
}
trap cleanup EXIT

verify_checksum "${BACKUP_FILE}"

case "${BACKUP_FILE}" in
    *.age)
        command -v age >/dev/null
        BACKUP_AGE_IDENTITY_FILE="${BACKUP_AGE_IDENTITY_FILE:?BACKUP_AGE_IDENTITY_FILE is required for age restores}"
        age -i "${BACKUP_AGE_IDENTITY_FILE}" -d -o "${restore_path}" "${BACKUP_FILE}"
        ;;
    *.gpg)
        command -v gpg >/dev/null
        if [[ -n "${BACKUP_PASSPHRASE:-}" ]]; then
            printf '%s' "${BACKUP_PASSPHRASE}" | gpg --batch --yes --pinentry-mode loopback \
                --passphrase-fd 0 --decrypt --output "${restore_path}" "${BACKUP_FILE}"
        else
            gpg --batch --yes --decrypt --output "${restore_path}" "${BACKUP_FILE}"
        fi
        ;;
    *)
        restore_path="${BACKUP_FILE}"
        ;;
esac

if [[ "${DB_MODE}" == "compose" ]]; then
    docker compose exec -T db pg_restore -U "${DB_USER}" -d "${DB_NAME}" \
        --single-transaction --clean --if-exists --no-owner --no-acl < "${restore_path}"
    docker compose exec -T db psql -U "${DB_USER}" -d "${DB_NAME}" \
        -At -c "SELECT count(*) FROM django_migrations;"
else
    PGPASSWORD="${DB_PASSWORD:?DB_PASSWORD is required}" pg_restore \
        -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
        --single-transaction --clean --if-exists --no-owner --no-acl "${restore_path}"
    PGPASSWORD="${DB_PASSWORD}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" \
        -d "${DB_NAME}" -At -c "SELECT count(*) FROM django_migrations;"
fi

printf 'Restored PostgreSQL backup into %s.\n' "${DB_NAME}"
