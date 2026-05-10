#!/usr/bin/env bash
# Daily backup for the bjj_bot SQLite database.
#
# Strategy:
#   1. sqlite3 .backup → safe online snapshot (works while the bot writes).
#   2. gzip -9 the snapshot.
#   3. Copy to /data/backups/ (on devbox host: /home/timamz/dev/bjj-tracker/data/backups/).
#   4. Upload to Yandex Disk WebDAV at /bjj-bot-backups/.
#   5. Prune local + remote files older than RETENTION_DAYS.
#   6. On any failure, notify OWNER_ID via the bot (SOCKS proxy honored).
#
# Invoked by host cron: `docker exec bjj-bot /app/scripts/backup.sh`.
# The live DB is never modified — only read via SQLite's online backup API.

set -euo pipefail

: "${DB_PATH:=/data/bjj_bot.sqlite3}"
: "${LOCAL_BACKUP_DIR:=/data/backups}"
: "${WEBDAV_BASE:=https://webdav.yandex.com}"
: "${WEBDAV_DIR:=/bjj-bot-backups}"
: "${RETENTION_DAYS:=30}"

require() {
    local var="$1"
    if [[ -z "${!var:-}" ]]; then
        echo "missing required env: ${var}" >&2
        exit 2
    fi
}
require BOT_TOKEN
require OWNER_ID
require YANDEX_LOGIN
require YANDEX_APP_PASSWORD

STAMP="$(date -u +%Y-%m-%dT%H%M%SZ)"
FILENAME="bjj_bot-${STAMP}.sqlite3.gz"
TMP_DB="/tmp/bjj_bot-${STAMP}.sqlite3"
LOCAL_PATH="${LOCAL_BACKUP_DIR}/${FILENAME}"

LOG_FILE="/tmp/bjj-backup-${STAMP}.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

tg_proxy_args=()
if [[ -n "${PROXY_URL:-}" ]]; then
    tg_proxy_args=(--proxy "${PROXY_URL/socks5:/socks5h:}")
fi

notify_failure() {
    local step="$1"
    local tail_log
    tail_log="$(tail -n 20 "${LOG_FILE}" 2>/dev/null || true)"
    local text="bjj_bot backup FAILED at step: ${step}
stamp: ${STAMP}
---
${tail_log}"
    curl -sS --max-time 30 "${tg_proxy_args[@]}" \
        -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${OWNER_ID}" \
        --data-urlencode "text=${text}" >/dev/null || true
}

CURRENT_STEP="init"
trap 'notify_failure "${CURRENT_STEP}"' ERR

cleanup() {
    rm -f "${TMP_DB}" "${TMP_DB}.gz"
}
trap 'cleanup; notify_failure "${CURRENT_STEP}"' ERR
trap 'cleanup' EXIT

mkdir -p "${LOCAL_BACKUP_DIR}"

CURRENT_STEP="sqlite3 .backup"
sqlite3 "${DB_PATH}" ".backup '${TMP_DB}'"

CURRENT_STEP="gzip"
gzip -9 "${TMP_DB}"
GZ_SRC="${TMP_DB}.gz"

CURRENT_STEP="local copy"
cp "${GZ_SRC}" "${LOCAL_PATH}"

AUTH="${YANDEX_LOGIN}:${YANDEX_APP_PASSWORD}"

CURRENT_STEP="webdav mkcol"
# MKCOL is idempotent for our purposes: 201 = created, 405 = already exists. Both fine.
mkcol_code="$(curl -sS -o /dev/null -w '%{http_code}' -u "${AUTH}" -X MKCOL "${WEBDAV_BASE}${WEBDAV_DIR}/")"
if [[ "${mkcol_code}" != "201" && "${mkcol_code}" != "405" ]]; then
    echo "unexpected MKCOL response: ${mkcol_code}" >&2
    exit 1
fi

CURRENT_STEP="webdav upload"
curl -fsS -u "${AUTH}" -T "${GZ_SRC}" "${WEBDAV_BASE}${WEBDAV_DIR}/${FILENAME}"

CURRENT_STEP="prune local"
find "${LOCAL_BACKUP_DIR}" -maxdepth 1 -name 'bjj_bot-*.sqlite3.gz' -type f -mtime "+${RETENTION_DAYS}" -delete

CURRENT_STEP="prune remote"
propfind_body="$(curl -fsS -u "${AUTH}" -X PROPFIND -H 'Depth: 1' "${WEBDAV_BASE}${WEBDAV_DIR}/")"
names="$(printf '%s' "${propfind_body}" | grep -oE 'bjj_bot-[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z\.sqlite3\.gz' | sort -u || true)"
now_epoch="$(date -u +%s)"
cutoff=$(( now_epoch - RETENTION_DAYS * 86400 ))
while IFS= read -r name; do
    [[ -z "${name}" ]] && continue
    date_part="${name#bjj_bot-}"
    date_part="${date_part%%Z.sqlite3.gz}"
    # date_part is YYYY-MM-DDTHHMMSS — rewrite to something `date -d` understands.
    iso="${date_part:0:10}T${date_part:11:2}:${date_part:13:2}:${date_part:15:2}Z"
    file_epoch="$(date -u -d "${iso}" +%s 2>/dev/null || echo 0)"
    if (( file_epoch > 0 && file_epoch < cutoff )); then
        curl -fsS -o /dev/null -u "${AUTH}" -X DELETE "${WEBDAV_BASE}${WEBDAV_DIR}/${name}" || true
    fi
done <<< "${names}"

CURRENT_STEP="done"
echo "backup ok: ${FILENAME} ($(stat -c%s "${LOCAL_PATH}" 2>/dev/null || echo '?') bytes)"
