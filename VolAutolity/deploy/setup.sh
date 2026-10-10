#!/usr/bin/env bash
# Idempotent setup of the VolAutolity worker (replaces the Ansible playbook).
# cloud-init runs it on first boot. After changing code under /opt/volautolity/app, re-run:
#   sudo bash /opt/volautolity/app/deploy/setup.sh
set -euo pipefail

readonly APP_DIR=/opt/volautolity
readonly VENV="$APP_DIR/venv"
readonly ENV_FILE=/etc/volautolity/volautolity.env
readonly SERVICE_USER=volautolity

log() { echo "[volautolity-setup] $*"; }

# Download over HTTPS and verify the pinned SHA-256. Spec format: <sha256>@<url>
fetch_verified() {
  local spec="$1" dest="$2"
  local sha="${spec%%@*}" url="${spec#*@}" tmp
  tmp="$(mktemp)"
  if ! curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --retry 3 "$url" -o "$tmp"; then
    rm -f "$tmp"; log "WARNING: download failed: $url"; return 1
  fi
  if ! echo "$sha  $tmp" | sha256sum --check --status; then
    rm -f "$tmp"; log "WARNING: SHA-256 mismatch, refusing to install: $url"; return 1
  fi
  install -m 0644 "$tmp" "$dest"
  rm -f "$tmp"
}

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

id -u "$SERVICE_USER" &>/dev/null || useradd --system --no-create-home --home-dir /var/lib/volautolity --shell /usr/sbin/nologin "$SERVICE_USER"
chown root:"$SERVICE_USER" "$ENV_FILE"
chmod 0640 "$ENV_FILE"
# Linux/Mac ISF symbol files go here (scp them in); Windows symbols are downloaded automatically.
install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" /var/lib/volautolity /var/lib/volautolity/symbols

log "python environment"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --disable-pip-version-check --upgrade pip
"$VENV/bin/pip" install --quiet --disable-pip-version-check --requirement "$APP_DIR/app/requirements.txt"

plugin_dir="$("$VENV/bin/python" -c 'import os, volatility3.framework.plugins.windows as w; print(os.path.dirname(w.__file__))')"
for spec in ${COMMUNITY_PLUGINS:-}; do
  url="${spec#*@}"
  log "community plugin $url"
  fetch_verified "$spec" "$plugin_dir/$(basename "$url")" || true
done

if [[ -n "${YARA_RULES_FILE:-}" ]]; then
  log "YARA rules"
  install -d -m 0755 "$(dirname "$YARA_RULES_FILE")"
  combined="$(mktemp)"
  for spec in ${YARA_RULES:-}; do
    part="$(mktemp)"
    if fetch_verified "$spec" "$part"; then
      cat "$part" >> "$combined"
      echo >> "$combined"
    fi
    rm -f "$part"
  done
  if [[ -s "$combined" ]] && "$VENV/bin/python" -c 'import sys, yara; yara.compile(filepath=sys.argv[1])' "$combined"; then
    install -m 0644 "$combined" "$YARA_RULES_FILE"
  else
    log "WARNING: no valid YARA rules; YARA plugins will be skipped"
    rm -f "$YARA_RULES_FILE"
  fi
  rm -f "$combined"
fi

log "ClamAV signatures"
systemctl stop clamav-freshclam || true
freshclam --quiet || log "WARNING: freshclam failed; clamav-freshclam will retry"
systemctl enable --now clamav-freshclam

log "service"
install -m 0644 "$APP_DIR/app/deploy/volautolity.service" /etc/systemd/system/volautolity.service
# ProtectSystem=strict makes everything read-only; open up only the configurable work directory.
install -d -m 0755 /etc/systemd/system/volautolity.service.d
# "-" tolerates the path not existing yet; ExecStartPre creates it before the main process starts.
printf '[Service]\nReadWritePaths=-%s\n' "$WORK_DIR" > /etc/systemd/system/volautolity.service.d/work-dir.conf
systemctl daemon-reload
systemctl enable volautolity.service
systemctl restart volautolity.service
log "done"
