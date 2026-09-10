#!/usr/bin/env bash
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run this helper through omarchy-camguardctl." >&2; exit 1; }
[[ $# -eq 5 ]] || {
  echo "usage: update-service-system.sh <user> <group> <uid> <home> <photo-dir>" >&2
  exit 2
}

user_name=$1
user_group=$2
user_uid=$3
user_home=$4
photo_dir=$5

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
/usr/bin/python3 /usr/local/libexec/omarchy-camguard-render-service \
  "$template" "$unit_tmp" "$user_name" "$user_group" "$user_uid" "$user_home" "$photo_dir"
install -d -o "$user_name" -g "$user_group" -m 0700 "$photo_dir"
install -o root -g root -m 0644 "$unit_tmp" "$unit_path"
rm -f "$unit_tmp"
trap - EXIT

systemctl daemon-reload
systemctl restart omarchy-camguard.service
