#!/usr/bin/env bash
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run this helper through omarchy-camguardctl." >&2; exit 1; }
[[ $# -eq 4 || $# -eq 5 ]] || {
  echo "usage: update-service-system.sh <user> <group> <uid> <home> [photo-dir]" >&2
  exit 2
}

user_name=$1
user_group=$2
user_uid=$3
user_home=$4
photo_dir_arg=${5:-}

IFS=: read -r account _ account_uid account_gid _ account_home _ < <(getent passwd "$user_name")
[[ $account == "$user_name" && $account_uid == "$user_uid" && $account_home == "$user_home" ]] || {
  echo "User identity does not match the system account database." >&2
  exit 2
}
[[ $(getent group "$user_group" | cut -d: -f3) == "$account_gid" ]] || {
  echo "Group identity does not match the user's primary group." >&2
  exit 2
}

template=/etc/systemd/system/omarchy-camguard.service.in
[[ -f $template ]] || {
  echo "CamGuard service template is missing. Run ./install.sh first." >&2
  exit 1
}
[[ -x /usr/local/libexec/omarchy-camguard-render-service ]] || {
  echo "CamGuard service renderer is missing. Run ./install.sh first." >&2
  exit 1
}

unit_path=/etc/systemd/system/omarchy-camguard.service
unit_tmp=$(mktemp "${unit_path}.XXXXXX")
trap 'rm -f "$unit_tmp"' EXIT
render_args=(
  /usr/bin/python3
  /usr/local/libexec/omarchy-camguard-render-service
  "$template"
  "$unit_tmp"
  "$user_name"
  "$user_group"
  "$user_uid"
  "$user_home"
)
# Prefer the optional argv only when present; otherwise the renderer reads
# photoDirectory from the user config (keeps UTF-8 / emoji paths out of pkexec).
if [[ -n $photo_dir_arg ]]; then
  render_args+=("$photo_dir_arg")
fi
"${render_args[@]}"

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

# FUSE mounts (pCloud/rclone) reject root creates; ensure the dir as the owner.
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
systemctl restart omarchy-camguard.service
