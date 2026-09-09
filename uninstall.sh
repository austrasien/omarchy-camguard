#!/usr/bin/env bash
set -euo pipefail

plugin_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
user_name=$(id -un)
user_uid=$(id -u)
IFS=: read -r _ _ _ _ _ account_home _ < <(getent passwd "$user_name")

pkexec "$plugin_dir/uninstall-system.sh" "$user_name" "$user_uid" "$account_home"
rm -rf "${XDG_RUNTIME_DIR:-/run/user/$user_uid}/omarchy-camguard"

echo "Run 'omarchy plugin remove austraz.camguard' to remove the panel itself."
