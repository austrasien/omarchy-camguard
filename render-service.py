#!/usr/bin/env bash
# Render the CamGuard systemd unit from the installed template.
# usage: render-service.py <template> <destination> <user> <group> <uid> <home> [photo-dir]
import json
import sys
from pathlib import Path

source, destination, user, group, uid, home, *rest = sys.argv[1:]
home_path = Path(home).resolve()
config_path = home_path / ".config" / "omarchy-camguard" / "config.json"

photo_dir = rest[0] if rest else ""
if not photo_dir:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            photo_dir = str(payload.get("photoDirectory") or "")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        photo_dir = ""

if not photo_dir:
    photo_dir = str(home_path / "Pictures" / "CamGuard")

raw = Path(photo_dir).expanduser()
if not raw.is_absolute():
    raw = home_path / raw
photo_path = raw.resolve()
try:
    photo_path.relative_to(home_path)
except ValueError as error:
    raise SystemExit(f"Photo directory must stay under the user home: {error}") from error

text = Path(source).read_text(encoding="utf-8")
for marker, value in {
    "@USER@": user,
    "@GROUP@": group,
    "@UID@": uid,
    "@HOME@": str(home_path),
    "@PHOTO_DIR@": str(photo_path),
}.items():
    text = text.replace(marker, value)
if "@" in text:
    raise SystemExit("Unresolved service template marker")
Path(destination).write_text(text, encoding="utf-8")
