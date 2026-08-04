# Backup And Restore Runbook

Gift Manager stores durable application data in PostgreSQL and, when uploads are
enabled, the media volume. A deployment is not considered recoverable until a
recent encrypted backup has been restored into a clean environment and checked.

## Environment

Required backup settings:

- `BACKUP_DIR`: local staging directory for encrypted backup files and manifests.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`: PostgreSQL target.
- One encryption setting: `BACKUP_AGE_RECIPIENT`, `BACKUP_GPG_RECIPIENT`, or
  `BACKUP_PASSPHRASE`.
- `BACKUP_AGE_IDENTITY_FILE`: required when restoring `.age` backups.

Optional settings:

- `BACKUP_DB_MODE=compose`: run `pg_dump` or `pg_restore` through the Compose
  `db` container instead of connecting directly.
- `BACKUP_UPLOAD_CMD`: shell command run after encryption. It receives
  `BACKUP_FILE` and `BACKUP_MANIFEST` in the environment.
- `BACKUP_MONITOR_SUCCESS_URL` and `BACKUP_MONITOR_FAILURE_URL`: healthcheck
  URLs pinged after completed or failed PostgreSQL backups.
- `MEDIA_ROOT`: media directory to archive. Defaults to `media`.
- `MEDIA_BACKUP_ENABLED=true`: force media backups even when media is currently
  empty.

## Scheduled Backups

Run PostgreSQL backups at least nightly:

```bash
BACKUP_REASON=scheduled scripts/postgres_backup.sh
```

Run media backups when user-uploaded files are in use:

```bash
MEDIA_BACKUP_ENABLED=true scripts/media_backup.sh
```

Configure `BACKUP_UPLOAD_CMD` to copy the encrypted file and manifest to
off-host storage. Examples include `rclone`, `aws s3 cp`, or a managed backup
agent. The local `latest-*.manifest` files are only status pointers; they are
not a substitute for off-host storage.

Systemd templates are provided under `deploy/systemd/` for hosts that run the
Compose stack directly:

```bash
sudo mkdir -p /etc/gift-manager
sudo cp deploy/systemd/backup.env.example /etc/gift-manager/backup.env
sudo install -m 0644 deploy/systemd/gift-manager-*-backup.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/gift-manager-*-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gift-manager-postgres-backup.timer
sudo systemctl enable --now gift-manager-media-backup.timer
```

Edit `/etc/gift-manager/backup.env` before enabling the timers. The environment
file must include encryption and upload settings for production backups.

## Before Migrations

Production migrations must be a controlled release step, not part of image
builds or long-running web startup. Before running migrations:

```bash
BACKUP_REASON=pre-migration scripts/pre_migration_snapshot.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile release run --rm migrate
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d web nginx
```

Keep the generated manifest and migration plan with the release notes.

## Restore Drill

Restore into a clean database, never into live production unless this is an
approved recovery event:

```bash
createdb gift_manager_restore
DB_NAME=gift_manager_restore \
BACKUP_FILE=/path/to/gift_manager-20260730T000000Z.dump.age \
BACKUP_AGE_IDENTITY_FILE=/run/secrets/backup-age-identity.txt \
ALLOW_DESTRUCTIVE_RESTORE=yes \
scripts/postgres_restore.sh
```

Then point Django at the restored database and run:

```bash
python manage.py check
python manage.py showmigrations --plan
```

For media, decrypt the encrypted media archive with the same tool used for
backup, unpack it into the target media volume, and verify the app can serve or
link to restored files.

The restore script verifies a sibling `.sha256` file when one exists. Keep
backup files and checksum files together when copying artifacts between systems.

Schedule a quarterly restore drill. Use the latest off-host PostgreSQL artifact,
restore into a clean database, run Django checks, and record the observed restore
duration against the target RTO.

## Acceptance Criteria

- Latest PostgreSQL backup is encrypted and stored off-host.
- Failure and success monitor hooks are configured for scheduled backups.
- Restore into a clean database succeeds without manual SQL edits.
- A restore drill is performed at least quarterly and before major schema work.
- Rollback plans pair application image rollback with database restore or a
  tested forward migration.
