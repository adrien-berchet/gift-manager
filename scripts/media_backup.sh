#!/usr/bin/env bash
set -euo pipefail

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${BACKUP_DIR:?BACKUP_DIR is required}"
MEDIA_ROOT="${MEDIA_ROOT:-media}"

mkdir -p "${BACKUP_DIR}"

notify() {
    local url="${1:-}"
    if [[ -n "${url}" ]]; then
        curl -fsS --max-time 10 --output /dev/null "${url}" || true
    fi
}

if [[ ! -d "${MEDIA_ROOT}" ]]; then
    if [[ "${MEDIA_BACKUP_ENABLED:-false}" == "true" ]]; then
        echo "Media backup is enabled, but media directory does not exist: ${MEDIA_ROOT}" >&2
        exit 1
    fi
    echo "Media directory does not exist: ${MEDIA_ROOT}"
    exit 0
fi

if [[ "${MEDIA_BACKUP_ENABLED:-false}" != "true" ]] && [[ -z "$(find "${MEDIA_ROOT}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "Media backup skipped because media is empty and MEDIA_BACKUP_ENABLED is not true."
    exit 0
fi

tmp_dir="$(mktemp -d)"
archive_path="${tmp_dir}/media-${TIMESTAMP}.tar.gz"
manifest_path="${BACKUP_DIR}/media-${TIMESTAMP}.manifest"

cleanup() {
    local status=$?
    rm -rf "${tmp_dir}"
    if [[ ${status} -ne 0 ]]; then
        notify "${BACKUP_MONITOR_FAILURE_URL:-}"
    fi
    return "${status}"
}
trap cleanup EXIT

tar -czf "${archive_path}" -C "$(dirname "${MEDIA_ROOT}")" "$(basename "${MEDIA_ROOT}")"

if [[ -n "${BACKUP_AGE_RECIPIENT:-}" ]]; then
    command -v age >/dev/null
    encrypted_backup="${BACKUP_DIR}/media-${TIMESTAMP}.tar.gz.age"
    age -r "${BACKUP_AGE_RECIPIENT}" -o "${encrypted_backup}" "${archive_path}"
elif [[ -n "${BACKUP_GPG_RECIPIENT:-}" ]]; then
    command -v gpg >/dev/null
    encrypted_backup="${BACKUP_DIR}/media-${TIMESTAMP}.tar.gz.gpg"
    gpg --batch --yes --encrypt --recipient "${BACKUP_GPG_RECIPIENT}" \
        --output "${encrypted_backup}" "${archive_path}"
elif [[ -n "${BACKUP_PASSPHRASE:-}" ]]; then
    command -v gpg >/dev/null
    encrypted_backup="${BACKUP_DIR}/media-${TIMESTAMP}.tar.gz.gpg"
    printf '%s' "${BACKUP_PASSPHRASE}" | gpg --batch --yes --pinentry-mode loopback \
        --passphrase-fd 0 --symmetric --cipher-algo AES256 \
        --output "${encrypted_backup}" "${archive_path}"
else
    echo "Set BACKUP_AGE_RECIPIENT, BACKUP_GPG_RECIPIENT, or BACKUP_PASSPHRASE." >&2
    exit 1
fi

(
    cd "$(dirname "${encrypted_backup}")"
    sha256sum "$(basename "${encrypted_backup}")" > "$(basename "${encrypted_backup}").sha256"
)
{
    printf 'created_at=%s\n' "${TIMESTAMP}"
    printf 'media_root=%s\n' "${MEDIA_ROOT}"
    printf 'git_sha=%s\n' "$(git rev-parse HEAD 2>/dev/null || printf 'unknown')"
    printf 'backup_file=%s\n' "${encrypted_backup}"
    printf 'backup_sha256=%s\n' "$(cut -d ' ' -f 1 "${encrypted_backup}.sha256")"
    printf 'backup_bytes=%s\n' "$(wc -c < "${encrypted_backup}")"
} > "${manifest_path}"

if [[ -n "${BACKUP_UPLOAD_CMD:-}" ]]; then
    BACKUP_FILE="${encrypted_backup}" BACKUP_MANIFEST="${manifest_path}" sh -c "${BACKUP_UPLOAD_CMD}"
fi

cp "${manifest_path}" "${BACKUP_DIR}/latest-media.manifest"
notify "${BACKUP_MONITOR_SUCCESS_URL:-}"
printf 'Created encrypted media backup: %s\n' "${encrypted_backup}"
