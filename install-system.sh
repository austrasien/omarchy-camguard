#!/usr/bin/env bash
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run this helper through install.sh or omarchy-camguardctl." >&2; exit 1; }
[[ $# -eq 4 || $# -eq 5 ]] || {
  echo "usage: install-system.sh <user> <group> <uid> <home> [photo-dir]" >&2
  exit 2
}

plugin_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
user_name=$1
user_group=$2
user_uid=$3
user_home=$4
photo_dir_arg=${5:-}

[[ $user_name =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "Invalid user name." >&2; exit 2; }
[[ $user_group =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "Invalid group name." >&2; exit 2; }
[[ $user_uid =~ ^[0-9]+$ ]] || { echo "Invalid UID." >&2; exit 2; }
[[ $user_home == /* && $user_home != *$'\n'* ]] || { echo "Invalid home path." >&2; exit 2; }

IFS=: read -r account _ account_uid account_gid _ account_home _ < <(getent passwd "$user_name")
[[ $account == "$user_name" && $account_uid == "$user_uid" && $account_home == "$user_home" ]] || {
  echo "User identity does not match the system account database." >&2
  exit 2
}
[[ $(getent group "$user_group" | cut -d: -f3) == "$account_gid" ]] || {
  echo "Group identity does not match the user's primary group." >&2
  exit 2
}

install -d -m 0755 /usr/local/libexec
install -o root -g root -m 0755 \
  "$plugin_dir/daemon.py" \
  /usr/local/libexec/omarchy-camguard-daemon
install -o root -g root -m 0644 \
  "$plugin_dir/omarchy-camguard.service" \
  /etc/systemd/system/omarchy-camguard.service.in
install -o root -g root -m 0755 \
  "$plugin_dir/render-service.py" \
  /usr/local/libexec/omarchy-camguard-render-service

install -d -o "$user_name" -g "$user_group" -m 0700 \
  "$user_home/.local/state/omarchy-camguard" \
  "$user_home/.config/omarchy-camguard"
install -d -o "$user_name" -g "$user_group" -m 0755 "$user_home/.local/bin"
install -o "$user_name" -g "$user_group" -m 0755 \
  "$plugin_dir/bin/omarchy-camguardctl" \
  "$user_home/.local/bin/omarchy-camguardctl"

config_path="$user_home/.config/omarchy-camguard/config.json"
if [[ ! -e $config_path ]]; then
  install -o "$user_name" -g "$user_group" -m 0600 \
    "$plugin_dir/config.example.json" "$config_path"
else
  chown "$user_name:$user_group" "$config_path"
  chmod 0600 "$config_path"
fi

unit_path=/etc/systemd/system/omarchy-camguard.service
unit_tmp=$(mktemp "${unit_path}.XXXXXX")
trap 'rm -f "$unit_tmp"' EXIT
render_args=(
  /usr/local/libexec/omarchy-camguard-render-service
  /etc/systemd/system/omarchy-camguard.service.in
  "$unit_tmp"
  "$user_name"
  "$user_group"
  "$user_uid"
  "$user_home"
)
if [[ -n $photo_dir_arg ]]; then
  render_args+=("$photo_dir_arg")
fi
/usr/bin/python3 "${render_args[@]}"
photo_dir=$(
  /usr/bin/python3 - <<'PY' "$unit_tmp" "$user_home"
import json
import sys
from pathlib import Path

unit = Path(sys.argv[1])
home = Path(sys.argv[2])
for line in unit.read_text(encoding="utf-8").splitlines():
    if line.startswith("ReadWritePaths=") and "/.local/state/omarchy-camguard" not in line:
        value = line.split("=", 1)[1].strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        print(value)
        break
else:
    config = home / ".config" / "omarchy-camguard" / "config.json"
    try:
        payload = json.loads(config.read_text(encoding="utf-8"))
        print(str(payload.get("photoDirectory") or ""))
    except Exception:
        print("")
PY
)
# FUSE mounts reject root creates; create as the owning user instead.
if [[ -n $photo_dir ]]; then
  if ! runuser -u "$user_name" -- mkdir -p -- "$photo_dir" 2>/dev/null; then
    [[ -d $photo_dir ]] || {
      echo "Photo directory is missing and could not be created: $photo_dir" >&2
      exit 1
    }
  fi
fi
install -o root -g root -m 0644 "$unit_tmp" "$unit_path"
rm -f "$unit_tmp"
trap - EXIT

systemctl daemon-reload
systemctl enable omarchy-camguard.service
systemctl restart omarchy-camguard.service
