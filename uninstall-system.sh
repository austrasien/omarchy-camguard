#!/usr/bin/env bash
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run this helper through uninstall.sh." >&2; exit 1; }
[[ $# -eq 3 ]] || {
  echo "usage: uninstall-system.sh <user> <uid> <home>" >&2
  exit 2
}

user_name=$1
user_uid=$2
user_home=$3

IFS=: read -r account _ account_uid _ _ account_home _ < <(getent passwd "$user_name")
[[ $account == "$user_name" && $account_uid == "$user_uid" && $account_home == "$user_home" ]] || {
  echo "User identity does not match the system account database." >&2
  exit 2
}

systemctl disable --now omarchy-camguard.service 2>/dev/null || true
rm -f \
  /etc/systemd/system/omarchy-camguard.service \
  /etc/systemd/system/omarchy-camguard.service.in \
  /usr/local/libexec/omarchy-camguard-daemon \
  "$user_home/.local/bin/omarchy-camguardctl"
systemctl daemon-reload

echo "CamGuard service removed. Photos and configuration were preserved."
