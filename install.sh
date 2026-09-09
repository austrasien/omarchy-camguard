#!/usr/bin/env bash
set -euo pipefail

plugin_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

for command in ffmpeg notify-send omarchy omarchy-shell pkexec python3 systemctl; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Missing required command: $command" >&2
    exit 1
  }
done

[[ -e /dev/video0 ]] || {
  echo "No camera found at /dev/video0. Install anyway after configuring the camera path." >&2
  exit 1
}
compgen -G "/dev/input/event*" >/dev/null || {
  echo "No Linux input event devices were found." >&2
  exit 1
}

user_name=$(id -un)
user_group=$(id -gn)
user_uid=$(id -u)
IFS=: read -r _ _ _ _ _ account_home _ < <(getent passwd "$user_name")
[[ -n $account_home && $account_home == "$HOME" ]] || {
  echo "HOME does not match the system account database." >&2
  exit 1
}

if [[ $(omarchy-shell lock isLocked 2>/dev/null || true) == true ]]; then
  echo "Unlock the Omarchy session before installing CamGuard." >&2
  exit 1
fi

pkexec "$plugin_dir/install-system.sh" \
  "$user_name" "$user_group" "$user_uid" "$account_home"

omarchy restart shell
lock_state=""
for _ in {1..20}; do
  lock_state=$(omarchy-shell lock isLocked 2>/dev/null || true)
  [[ $lock_state == true || $lock_state == false ]] && break
  sleep 0.1
done
if [[ $lock_state == true || $lock_state == false ]]; then
  "$account_home/.local/bin/omarchy-camguardctl" lock-state "$lock_state"
fi

echo "CamGuard installed for $user_name."
