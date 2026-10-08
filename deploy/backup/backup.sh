#!/bin/sh
# Automatic PostgreSQL backups (the "backup" service in docker-compose.yml).
#
# Every BACKUP_INTERVAL_HOURS (default 6) it writes a compressed dump to /backups and deletes
# dumps older than BACKUP_KEEP_DAYS (default 14). /backups is a folder on the server
# (./backups next to docker-compose.yml).
#
# Off-site copy (recommended, free): with BACKUP_PASSPHRASE, TELEGRAM_BOT_TOKEN and
# OPS_TELEGRAM_CHAT_ID set, each dump is also encrypted (AES-256) and sent to the operations
# Telegram chat, so a dead server doesn't take the data with it. Without a passphrase nothing
# leaves the server: customer data is never uploaded unencrypted.
#
# Restore: see deploy/backup/RESTORE.md
set -eu

INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-6}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
# Telegram bots can upload files up to 50 MB.
MAX_UPLOAD_BYTES=49000000

backup_once() {
  stamp="$(date -u +%Y%m%d-%H%M)"
  file="/backups/replisto-${stamp}.dump"
  echo "[backup] dumping to ${file}"
  PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump -h db -U "${POSTGRES_USER:-app}" \
    -d "${POSTGRES_DB:-app}" -Fc -f "${file}.tmp"
  mv "${file}.tmp" "${file}"
  find /backups -name 'replisto-*.dump*' -mtime "+${KEEP_DAYS}" -delete

  if [ -n "${BACKUP_PASSPHRASE:-}" ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ] \
     && [ -n "${OPS_TELEGRAM_CHAT_ID:-}" ]; then
    openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE \
      -in "${file}" -out "${file}.enc"
    size="$(wc -c < "${file}.enc")"
    if [ "${size}" -lt "${MAX_UPLOAD_BYTES}" ]; then
      curl -sf -o /dev/null \
        -F "chat_id=${OPS_TELEGRAM_CHAT_ID}" \
        -F "caption=Replisto backup ${stamp} (encrypted)" \
        -F "document=@${file}.enc" \
        "${TELEGRAM_API_BASE:-https://api.telegram.org}/bot${TELEGRAM_BOT_TOKEN}/sendDocument" \
        && echo "[backup] off-site copy sent" \
        || echo "[backup] WARNING: off-site upload failed"
    else
      echo "[backup] WARNING: dump too large for Telegram (${size} bytes); kept locally only"
    fi
    rm -f "${file}.enc"
  fi
  echo "[backup] done"
}

# Wait for the database on first start.
until PGPASSWORD="${POSTGRES_PASSWORD}" pg_isready -h db -U "${POSTGRES_USER:-app}" >/dev/null 2>&1; do
  sleep 3
done

while true; do
  backup_once || echo "[backup] ERROR: backup failed"
  sleep "$((INTERVAL_HOURS * 3600))"
done
