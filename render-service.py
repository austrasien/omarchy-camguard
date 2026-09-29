#!/usr/bin/env python3
# Render the CamGuard systemd unit from the installed template.
# usage: render-service.py <template> <destination> <user> <group> <uid> <home> [photo-dir]
import json
import sys
from pathlib import Path


def decode_mount_point(raw: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and index + 3 < len(raw) and raw[index + 1 : index + 4].isdigit():
            out.append(chr(int(raw[index + 1 : index + 4], 8)))
            index += 4
            continue
        out.append(char)
        index += 1
    return "".join(out)


def mount_fstype(path: Path) -> str:
    best = ""
    best_len = -1
    target = str(path)
    try:
        lines = Path("/proc/mounts").read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        mountpoint = decode_mount_point(parts[1])
        fstype = parts[2]
        if target == mountpoint or target.startswith(mountpoint.rstrip("/") + "/"):
            if len(mountpoint) > best_len:
                best = fstype
                best_len = len(mountpoint)
    return best


def is_fuse_path(path: Path) -> bool:
    fstype = mount_fstype(path)
    return fstype.startswith("fuse") or fstype in {"fuse", "fuseblk"}


def systemd_quote(path: str) -> str:
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


source, destination, user, group, uid, home, *rest = sys.argv[1:]
home_path = Path(home).expanduser().resolve()
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

# User FUSE mounts (pCloud/rclone) cannot be bind-mounted by root for
# ProtectHome=read-only / ReadWritePaths. Open home writes instead and skip
# the photo-dir ReadWritePaths bind.
fuse_photo = is_fuse_path(photo_path)
protect_home = "no" if fuse_photo else "read-only"
photo_readwrite_line = (
    ""
    if fuse_photo
    else f"ReadWritePaths={systemd_quote(str(photo_path))}"
)

text = Path(source).read_text(encoding="utf-8")
for marker, value in {
    "@USER@": user,
    "@GROUP@": group,
    "@UID@": uid,
    "@HOME@": str(home_path),
    "@PHOTO_DIR@": str(photo_path),
    "@PROTECT_HOME@": protect_home,
    "@PHOTO_READWRITE_LINE@": photo_readwrite_line,
}.items():
    text = text.replace(marker, value)
# Drop a blank leftover line when the FUSE photo bind is omitted.
text = "\n".join(line for line in text.splitlines() if line.strip() != "") + "\n"
if "@" in text:
    raise SystemExit("Unresolved service template marker")
Path(destination).write_text(text, encoding="utf-8")
