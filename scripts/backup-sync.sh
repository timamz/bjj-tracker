#!/usr/bin/env bash
# Host-side catch-up sync for bjj_bot backups (run from host cron, NOT in the container).
#
# scripts/backup.sh (in the container, 05:00 MSK) always writes the snapshot to
# data/backups/ first and then uploads to Yandex Disk once. Yandex WebDAV regularly
# answers 500 / connection reset, so days went missing remotely. This script makes
# the remote copies eventually consistent: every local snapshot of the last
# RETENTION_DAYS is copied (with retries) to
#   1. Google Drive  (rclone remote "gdrive", root_folder_id = bjj-bot-backups folder)
#   2. Yandex Disk   (DISABLED; opt-in with YANDEX_SYNC=1)
# Nothing is ever deleted or overwritten; already-present files are skipped by size.
#
# Cron (host):  20 5,17 * * *  /home/timamz/dev/bjj-tracker/scripts/backup-sync.sh >> /home/timamz/bjj-backup-sync.log 2>&1
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_BACKUP_DIR="${LOCAL_BACKUP_DIR:-${REPO_DIR}/data/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
GDRIVE_REMOTE="${GDRIVE_REMOTE:-gdrive}"
RCLONE="${RCLONE:-$(command -v rclone || echo "$HOME/.local/bin/rclone")}"
export PATH="$HOME/.local/bin:$PATH"

exec 9>"/tmp/bjj-backup-sync.lock"
flock -n 9 || { echo "$(date -Is) another sync is running"; exit 0; }

# Read only the vars we need from .env (no sourcing arbitrary content).
env_get() { grep -E "^$1=" "${REPO_DIR}/.env" | head -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }
BOT_TOKEN="$(env_get BOT_TOKEN)"; OWNER_ID="$(env_get OWNER_ID)"; PROXY_URL="$(env_get PROXY_URL)"
YANDEX_LOGIN="$(env_get YANDEX_LOGIN)"; YANDEX_APP_PASSWORD="$(env_get YANDEX_APP_PASSWORD)"

log() { echo "$(date -Is) $*"; }
FAILED=()

notify_failure() {
    local args=()
    [[ -n "${PROXY_URL}" ]] && args=(--proxy "${PROXY_URL/socks5:/socks5h:}")
    curl -sS --max-time 30 "${args[@]}" -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${OWNER_ID}" \
        --data-urlencode "text=bjj_bot backup-sync FAILED: $*" >/dev/null || true
}

RC_COMMON=(--max-age "${RETENTION_DAYS}d" --include 'bjj_bot-*.sqlite3.gz' --retries 5 --low-level-retries 10 --retries-sleep 20s --size-only --no-traverse -v)

# --- Google Drive ---
if "${RCLONE}" listremotes 2>/dev/null | grep -qx "${GDRIVE_REMOTE}:"; then
    log "gdrive: copy start"
    if "${RCLONE}" copy "${LOCAL_BACKUP_DIR}" "${GDRIVE_REMOTE}:" "${RC_COMMON[@]}" 2>&1 | grep -E 'Copied \(new\)|ERROR|Failed|Transferred:.*[0-9]+ / [0-9]+' ; [[ ${PIPESTATUS[0]} -eq 0 ]]; then
        log "gdrive: ok"
    else
        log "gdrive: FAILED"; FAILED+=("google drive")
    fi
else
    log "gdrive: remote '${GDRIVE_REMOTE}' not configured, skipping"
fi

# --- Yandex Disk backfill (DISABLED by default; re-enable with YANDEX_SYNC=1) ---
if [[ "${YANDEX_SYNC:-0}" == "1" && -n "${YANDEX_LOGIN}" && -n "${YANDEX_APP_PASSWORD}" ]]; then
    log "yandex: backfill start"
    export RCLONE_CONFIG_YA_TYPE=webdav RCLONE_CONFIG_YA_URL=https://webdav.yandex.com RCLONE_CONFIG_YA_VENDOR=other
    export RCLONE_CONFIG_YA_USER="${YANDEX_LOGIN}"
    RCLONE_CONFIG_YA_PASS="$("${RCLONE}" obscure "${YANDEX_APP_PASSWORD}")"; export RCLONE_CONFIG_YA_PASS
    if "${RCLONE}" copy "${LOCAL_BACKUP_DIR}" "ya:bjj-bot-backups" "${RC_COMMON[@]}" 2>&1 | grep -E 'Copied \(new\)|ERROR|Failed' ; [[ ${PIPESTATUS[0]} -eq 0 ]]; then
        log "yandex: ok"
    else
        log "yandex: FAILED"; FAILED+=("yandex disk")
    fi
fi

if (( ${#FAILED[@]} )); then
    notify_failure "${FAILED[*]}"
    exit 1
fi
log "done"
