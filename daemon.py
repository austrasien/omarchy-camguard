#!/usr/bin/env python3
"""CamGuard daemon: detect locked-session activity and capture webcam photos.

The daemon deliberately records only that an input event happened. It never
stores key codes, pointer coordinates, or raw input events.
"""

from __future__ import annotations

import ctypes
import glob
import json
import os
import select
import selectors
import signal
import struct
import subprocess
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


HOME = Path(os.environ.get("HOME", str(Path.home())))
CONFIG_PATH = HOME / ".config" / "omarchy-camguard" / "config.json"
STATE_DIR = HOME / ".local" / "state" / "omarchy-camguard"
STATUS_PATH = STATE_DIR / "status.json"
SESSION_PATH = STATE_DIR / "active-session.json"
DEFAULT_PHOTO_DIR = HOME / "Pictures" / "CamGuard"
RUNTIME_DIR = Path(
    os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
) / "omarchy-camguard"
LOCK_STATE_PATH = RUNTIME_DIR / "lock-state.json"
INPUT_EVENT = struct.Struct("llHHi")
INOTIFY_EVENT = struct.Struct("iIII")

IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_IGNORED = 0x00008000
INOTIFY_MASK = (
    IN_CLOSE_WRITE
    | IN_MOVED_TO
    | IN_CREATE
    | IN_DELETE
    | IN_DELETE_SELF
    | IN_MOVE_SELF
)

EV_KEY = 0x01
EV_REL = 0x02
EV_ABS = 0x03
EV_SW = 0x05
SW_LID = 0x00
BTN_TOUCH = 0x14A
POINTER_POSITION_CODES = {0x00, 0x01, 0x35, 0x36}

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "camera": "/dev/video0",
    "resolution": "1280x720",
    "intervalSeconds": 5,
    "retentionSeconds": 86400,
    "photoDirectory": str(DEFAULT_PHOTO_DIR),
}

# One activity window = 1 immediate + 2 follow-ups. A normal laptop unlock is often
# lid open (one burst) then password typing (second burst) → up to 6 photos.
UNLOCK_DELETE_COUNT = 6

TRIGGER_FILENAMES = {
    "lid": "opening_computer_case",
    "keyboard": "key_pressed",
    "trackpad": "trackpad_touched",
    "mouse": "mouse_moved",
}

running = True


def stop(_signum: int, _frame: object) -> None:
    global running
    running = False


def load_config() -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    try:
        payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            config.update(payload)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    config["enabled"] = bool(config.get("enabled", True))
    config["intervalSeconds"] = max(1, int(config.get("intervalSeconds", 5)))
    config["retentionSeconds"] = max(60, int(config.get("retentionSeconds", 86400)))
    config["camera"] = str(config.get("camera", "/dev/video0"))
    config["resolution"] = str(config.get("resolution", "1280x720"))
    config["photoDirectory"] = str(config.get("photoDirectory", DEFAULT_PHOTO_DIR))
    return config


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, separators=(",", ":"), sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def read_lock_state() -> tuple[bool | None, int]:
    payload = read_json(LOCK_STATE_PATH)
    locked = payload.get("locked")
    if not isinstance(locked, bool):
        return None, 0
    try:
        generation = max(0, int(payload.get("generation", 0)))
    except (TypeError, ValueError):
        generation = 0
    return locked, generation


class InotifyFile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.libc.inotify_init1.argtypes = [ctypes.c_int]
        self.libc.inotify_init1.restype = ctypes.c_int
        self.libc.inotify_add_watch.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint32,
        ]
        self.libc.inotify_add_watch.restype = ctypes.c_int
        self.fd = self.libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        self.watch_descriptor = -1
        self.last_arm_attempt = 0.0
        self.arm(force=True)

    def fileno(self) -> int:
        return self.fd

    def arm(self, force: bool = False) -> None:
        if self.watch_descriptor >= 0:
            return
        now = time.monotonic()
        if not force and now - self.last_arm_attempt < 1:
            return
        self.last_arm_attempt = now
        if not self.path.parent.is_dir():
            return
        descriptor = self.libc.inotify_add_watch(
            self.fd,
            os.fsencode(self.path.parent),
            INOTIFY_MASK,
        )
        if descriptor >= 0:
            self.watch_descriptor = descriptor

    def changed(self) -> bool:
        self.arm()
        changed = False
        while True:
            try:
                data = os.read(self.fd, 4096)
            except BlockingIOError:
                break
            except OSError:
                self.watch_descriptor = -1
                break
            if not data:
                break
            offset = 0
            while offset + INOTIFY_EVENT.size <= len(data):
                _wd, mask, _cookie, length = INOTIFY_EVENT.unpack_from(data, offset)
                offset += INOTIFY_EVENT.size
                raw_name = data[offset : offset + length]
                offset += length
                name = raw_name.split(b"\0", 1)[0].decode(errors="replace")
                if name == self.path.name:
                    changed = True
                if mask & IN_IGNORED:
                    self.watch_descriptor = -1
        self.arm()
        return changed

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


class InputMonitor:
    def __init__(self) -> None:
        self.selector = selectors.DefaultSelector()
        self.files: dict[int, Any] = {}
        self.paths: dict[int, str] = {}
        self.buffers: dict[int, bytes] = {}
        self.kinds: dict[int, str] = {}
        self.last_refresh = 0.0

    def close(self) -> None:
        for stream in list(self.files.values()):
            try:
                self.selector.unregister(stream)
            except Exception:
                pass
            try:
                stream.close()
            except OSError:
                pass
        self.files.clear()
        self.paths.clear()
        self.buffers.clear()
        self.kinds.clear()

    @staticmethod
    def device_kind(path: str) -> str:
        event_name = Path(path).name
        device_path = Path("/sys/class/input") / event_name / "device"
        try:
            name = (device_path / "name").read_text(encoding="utf-8").strip().lower()
        except OSError:
            return ""
        if name == "lid switch":
            return "lid"
        if "touchpad" in name:
            return "trackpad"
        if "keyboard" in name:
            return "keyboard"
        if "mouse" in name:
            try:
                siblings = device_path.resolve().parent.glob("input*")
                for sibling in siblings:
                    sibling_name = (sibling / "name").read_text(encoding="utf-8").lower()
                    if "touchpad" in sibling_name:
                        return "trackpad"
            except OSError:
                pass
            return "mouse"
        return ""

    def refresh(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last_refresh < 10:
            return
        self.last_refresh = now

        current_paths = {path: fd for fd, path in self.paths.items()}
        wanted = {
            os.path.realpath(path)
            for path in glob.glob("/dev/input/event*")
            if self.device_kind(path)
        }

        for path in wanted - current_paths.keys():
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
                stream = os.fdopen(fd, "rb", buffering=0)
                self.files[fd] = stream
                self.paths[fd] = path
                self.buffers[fd] = b""
                self.kinds[fd] = self.device_kind(path)
                self.selector.register(stream, selectors.EVENT_READ)
            except OSError:
                continue

        for path in current_paths.keys() - wanted:
            fd = current_paths[path]
            stream = self.files.pop(fd)
            self.paths.pop(fd, None)
            self.buffers.pop(fd, None)
            self.kinds.pop(fd, None)
            try:
                self.selector.unregister(stream)
            except Exception:
                pass
            stream.close()

    @staticmethod
    def is_trigger(kind: str, event_type: int, code: int, value: int) -> bool:
        if kind == "lid":
            return event_type == EV_SW and code == SW_LID and value == 0
        if kind == "keyboard":
            return event_type == EV_KEY and value == 1
        if kind == "trackpad":
            return (
                event_type == EV_KEY and code == BTN_TOUCH and value == 1
            ) or (
                event_type in {EV_REL, EV_ABS}
                and code in POINTER_POSITION_CODES
                and value != 0
            )
        if kind == "mouse":
            return (
                event_type == EV_REL
                and code in POINTER_POSITION_CODES
                and value != 0
            )
        return False

    def poll(self, timeout: float) -> list[str]:
        self.refresh()
        triggers: list[str] = []
        try:
            ready = self.selector.select(timeout)
        except OSError:
            return triggers

        for key, _mask in ready:
            stream = key.fileobj
            fd = stream.fileno()
            kind = self.kinds.get(fd, "")
            try:
                chunk = os.read(fd, INPUT_EVENT.size * 64)
            except BlockingIOError:
                continue
            except OSError:
                continue
            if not chunk:
                continue

            data = self.buffers.get(fd, b"") + chunk
            offset = 0
            while offset + INPUT_EVENT.size <= len(data):
                _sec, _usec, event_type, code, value = INPUT_EVENT.unpack_from(data, offset)
                offset += INPUT_EVENT.size
                if self.is_trigger(kind, event_type, code, value):
                    if kind not in {"mouse", "trackpad"} or kind not in triggers:
                        triggers.append(kind)
            self.buffers[fd] = data[offset:]
        return triggers


def capture(config: dict[str, Any], trigger_kind: str) -> tuple[str, str]:
    photo_root = Path(config["photoDirectory"]).expanduser()
    now = datetime.now().astimezone()
    day_directory = photo_root / now.strftime("%Y-%m-%d")
    day_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    prefix = TRIGGER_FILENAMES.get(trigger_kind, "unknown_trigger")
    timestamp = now.strftime("%Y%m%d-%H%M%S-%f")[:-3]
    output = day_directory / f"{prefix}-{timestamp}.png"
    temporary = day_directory / f".{prefix}-{timestamp}.tmp"

    command = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "v4l2",
        "-input_format",
        "mjpeg",
        "-video_size",
        config["resolution"],
        "-i",
        config["camera"],
        "-frames:v",
        "1",
        "-c:v",
        "png",
        "-compression_level",
        "3",
        "-f",
        "image2",
        "-y",
        str(temporary),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=12,
        )
    except subprocess.TimeoutExpired:
        return "", "Camera capture timed out"
    except OSError as error:
        return "", f"Unable to start ffmpeg: {error}"

    if result.returncode != 0:
        temporary.unlink(missing_ok=True)
        detail = result.stderr.strip().splitlines()
        return "", detail[-1][:240] if detail else f"ffmpeg exited with {result.returncode}"

    try:
        os.chmod(temporary, 0o600)
        file_descriptor = os.open(temporary, os.O_RDONLY | os.O_CLOEXEC)
        try:
            os.fsync(file_descriptor)
        finally:
            os.close(file_descriptor)
        os.replace(temporary, output)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        return "", f"Unable to publish camera image: {error}"
    return str(output), ""


def stored_photo_paths(config: dict[str, Any]) -> list[Path]:
    root = Path(config["photoDirectory"]).expanduser()
    if not root.exists():
        return []
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ]


def cleanup(config: dict[str, Any]) -> None:
    root = Path(config["photoDirectory"]).expanduser()
    cutoff = time.time() - int(config["retentionSeconds"])
    if not root.exists():
        return

    for photo in stored_photo_paths(config):
        try:
            if photo.is_file() and photo.stat().st_mtime < cutoff:
                photo.unlink()
        except OSError:
            continue
    for directory in sorted(root.glob("*"), reverse=True):
        try:
            if directory.is_dir():
                directory.rmdir()
        except OSError:
            pass


def stored_photo_count(config: dict[str, Any]) -> int:
    return len(stored_photo_paths(config))


def session_has_photos(session: dict[str, Any]) -> bool:
    records = session.get("photos")
    return isinstance(records, list) and len(records) > 0


def notify_intruder_photos(photo_count: int, open_path: str = "") -> bool:
    if photo_count <= 0:
        return False

    noun = "photo reste" if photo_count == 1 else "photos restent"
    body = f"{photo_count} {noun} à vérifier après le déverrouillage."
    if open_path:
        body += " Cliquez pour ouvrir."
    environment = os.environ.copy()
    environment.setdefault(
        "DBUS_SESSION_BUS_ADDRESS",
        f"unix:path={RUNTIME_DIR.parent / 'bus'}",
    )

    # Prefer a real PNG path for both the toast thumbnail (--image) and the app
    # icon slot (-i). Themed names like "camera-photo" paint Qt's broken-image
    # checkerboard in austraz.notifications (same class of bug as Cursor CLI).
    image_path = ""
    if open_path:
        target = Path(open_path)
        try:
            if target.is_file():
                image_path = str(target.resolve())
        except OSError:
            image_path = ""

    command: list[str]
    if Path("/usr/bin/omarchy-notification-send").is_file():
        command = [
            "/usr/bin/omarchy-notification-send",
            "--app-name",
            "CamGuard",
            "-u",
            "critical",
        ]
        if image_path:
            command.extend(["-i", image_path, "--image", image_path])
        else:
            command.extend(["-g", "󰄀"])
        command.extend(["CamGuard — Intrus photographié", body])
        if image_path:
            command.extend(["--exec", "xdg-open", image_path])
    else:
        command = [
            "/usr/bin/notify-send",
            "--app-name=CamGuard",
            "--urgency=critical",
            "CamGuard — Intrus photographié",
            body,
        ]
        if image_path:
            command.append(f"--icon={image_path}")

    try:
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"notification failed: {error}", flush=True)
        return False

    if result.returncode != 0:
        detail = result.stderr.strip()
        print(
            f"notification failed: {detail or f'{command[0]} exited with {result.returncode}'}",
            flush=True,
        )
        return False
    return True


def start_or_resume_session(lock_generation: int) -> None:
    session = read_json(SESSION_PATH)
    try:
        existing_generation = int(session.get("lockGeneration", -1))
    except (TypeError, ValueError):
        existing_generation = -1
    if (
        session.get("active") is True
        and existing_generation == lock_generation
    ):
        return
    atomic_json(
        SESSION_PATH,
        {
            "version": 1,
            "id": str(uuid.uuid4()),
            "active": True,
            "lockGeneration": lock_generation,
            "startedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "photos": [],
        },
    )


def record_session_photo(photo: str, trigger_kind: str) -> None:
    session = read_json(SESSION_PATH)
    if session.get("active") is not True:
        return
    photos = session.get("photos")
    if not isinstance(photos, list):
        photos = []
    photos.append(
        {
            "path": photo,
            "trigger": trigger_kind,
            "capturedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    )
    session["photos"] = photos
    atomic_json(SESSION_PATH, session)


def finish_session(
    config: dict[str, Any], delete_count: int = UNLOCK_DELETE_COUNT
) -> tuple[int, list[Path]]:
    """Drop the newest session photos on unlock.

    Returns ``(deleted, remaining_session_photos)``. Remaining paths are only
    files still on disk that belong to this session — not older leftovers in the
    photo directory (those must not trigger an intruder alert).
    """
    session = read_json(SESSION_PATH)
    if session.get("active") is not True:
        return 0, []
    records = session.get("photos")
    if not isinstance(records, list):
        records = []
    root = Path(config["photoDirectory"]).expanduser().resolve()
    delete_paths = {
        Path(str(record.get("path", "")))
        for record in records[-delete_count:]
        if isinstance(record, dict)
    }
    deleted = 0
    remaining_paths: list[Path] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        photo = Path(str(record.get("path", "")))
        try:
            photo.resolve().relative_to(root)
        except (OSError, ValueError):
            continue
        if photo in delete_paths:
            try:
                if photo.is_file():
                    photo.unlink()
                    deleted += 1
            except OSError:
                if photo.is_file():
                    remaining_paths.append(photo)
        elif photo.is_file():
            remaining_paths.append(photo)
    session["active"] = False
    session["endedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
    session["deletedAtUnlock"] = deleted
    atomic_json(SESSION_PATH, session)
    return deleted, remaining_paths


def latest_photo(config: dict[str, Any]) -> str:
    photos = stored_photo_paths(config)
    try:
        return str(max(photos, key=lambda path: path.stat().st_mtime))
    except (ValueError, OSError):
        return ""


class CaptureSchedule:
    def __init__(self, interval_seconds: int) -> None:
        self.interval_seconds = interval_seconds
        self.active = False
        self.trigger_kind = ""
        self.next_capture = 0.0
        self.remaining = 0

    def reset(self) -> None:
        self.active = False
        self.trigger_kind = ""
        self.next_capture = 0.0
        self.remaining = 0

    def trigger(self, trigger_kind: str, now: float) -> bool:
        capture_immediately = not self.active
        self.active = True
        self.trigger_kind = trigger_kind
        self.next_capture = now + self.interval_seconds
        self.remaining = 2
        return capture_immediately

    def due(self, now: float) -> str:
        if not self.active or now < self.next_capture:
            return ""
        trigger_kind = self.trigger_kind
        self.remaining -= 1
        if self.remaining <= 0:
            self.reset()
        else:
            self.next_capture += self.interval_seconds
        return trigger_kind


class LockStateMachine:
    def __init__(self) -> None:
        self.value: bool | None = None

    def observe(self, observed: bool | None) -> str:
        if observed is None:
            return ""
        previous = self.value
        self.value = observed
        if observed and previous is not True:
            return "locked"
        if not observed and previous is True:
            return "unlocked"
        return ""


def main() -> int:
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    monitor = InputMonitor()
    lock_watch = InotifyFile(LOCK_STATE_PATH)
    config_watch = InotifyFile(CONFIG_PATH)
    config = load_config()
    schedule = CaptureSchedule(config["intervalSeconds"])

    lock_state = LockStateMachine()
    lock_generation = 0
    armed = False
    last_trigger_kind = ""
    last_photo = ""
    photo_count = 0
    last_error = ""
    next_cleanup = 0.0
    next_status = 0.0
    next_lock_reconcile = 0.0
    next_config_reconcile = 0.0
    previous_enabled = config["enabled"]

    def take_photo(trigger_kind: str) -> None:
        nonlocal last_photo, photo_count, last_error
        photo, error = capture(config, trigger_kind)
        if photo:
            record_session_photo(photo, trigger_kind)
            last_photo = photo
            photo_count += 1
            last_error = ""
        else:
            last_error = error

    print("lock bridge: waiting for state", flush=True)

    try:
        while running:
            now = time.monotonic()

            if config_watch.changed() or now >= next_config_reconcile:
                config = load_config()
                schedule.interval_seconds = config["intervalSeconds"]
                next_config_reconcile = now + 30

            lock_file_changed = lock_watch.changed()
            if lock_file_changed or now >= next_lock_reconcile:
                observed_locked, observed_generation = read_lock_state()
                next_lock_reconcile = now + (0.5 if observed_locked is None else 30)

                if observed_locked is not None:
                    lock_generation = observed_generation
                    transition = lock_state.observe(observed_locked)

                    if transition == "locked":
                        start_or_resume_session(lock_generation)
                        schedule.reset()
                        last_trigger_kind = ""
                        armed = bool(config["enabled"])
                        print(
                            f"locked: monitoring {'armed' if armed else 'disabled'} "
                            f"(generation {lock_generation})",
                            flush=True,
                        )
                    elif transition == "unlocked":
                        finished_session = read_json(SESSION_PATH)
                        deleted, remaining_paths = finish_session(config)
                        remaining_session = len(remaining_paths)
                        photo_count = stored_photo_count(config)
                        last_photo = latest_photo(config)
                        armed = False
                        schedule.reset()
                        monitor.close()
                        # Alert only when THIS lock session still has evidence after
                        # hygiene. Leftovers from older sessions must not re-alert on
                        # every password unlock.
                        if session_has_photos(finished_session) and remaining_session > 0:
                            open_target = str(remaining_paths[-1])
                            notify_intruder_photos(remaining_session, open_target)
                        print(
                            f"unlocked: deleted {deleted} photo(s) from active session"
                            + (
                                f", {remaining_session} remain"
                                if remaining_session
                                else ""
                            ),
                            flush=True,
                        )

            enabled = bool(config["enabled"])
            if enabled != previous_enabled:
                if not enabled:
                    armed = False
                    schedule.reset()
                    monitor.close()
                elif lock_state.value is True:
                    start_or_resume_session(lock_generation)
                    armed = True
                previous_enabled = enabled

            locked = lock_state.value is True
            if enabled and locked and armed:
                monitor.refresh(force=not monitor.files)
                timeout = 0.5
                if schedule.active:
                    timeout = max(
                        0.0,
                        min(timeout, schedule.next_capture - time.monotonic()),
                    )
                triggers = monitor.poll(timeout)
                for trigger_kind in triggers:
                    trigger_time = time.monotonic()
                    capture_immediately = schedule.trigger(trigger_kind, trigger_time)
                    last_trigger_kind = trigger_kind
                    if capture_immediately:
                        print(f"trigger: {trigger_kind}", flush=True)
                        take_photo(trigger_kind)

                due_kind = schedule.due(time.monotonic())
                if due_kind:
                    take_photo(due_kind)
            else:
                monitor.close()
                readable = [lock_watch.fileno(), config_watch.fileno()]
                try:
                    select.select(readable, [], [], 0.5)
                except (OSError, ValueError):
                    time.sleep(0.5)

            now = time.monotonic()
            if now >= next_cleanup:
                cleanup(config)
                next_cleanup = now + 300

            if now >= next_status or lock_file_changed:
                session = read_json(SESSION_PATH)
                atomic_json(
                    STATUS_PATH,
                    {
                        "serviceActive": True,
                        "enabled": enabled,
                        "lockState": (
                            "unknown"
                            if lock_state.value is None
                            else "locked"
                            if lock_state.value
                            else "unlocked"
                        ),
                        "locked": locked,
                        "armed": bool(enabled and locked and armed),
                        "capturing": bool(
                            enabled and locked and armed and schedule.active
                        ),
                        "photoCount": photo_count,
                        "lastPhoto": last_photo,
                        "lastTrigger": last_trigger_kind,
                        "lastError": last_error,
                        "sessionId": str(session.get("id", "")),
                        "camera": config["camera"],
                        "updatedAt": datetime.now()
                        .astimezone()
                        .isoformat(timespec="seconds"),
                    },
                )
                next_status = now + 1
    finally:
        monitor.close()
        lock_watch.close()
        config_watch.close()

    atomic_json(
        STATUS_PATH,
        {
            "serviceActive": False,
            "enabled": load_config()["enabled"],
            "locked": False,
            "lockState": "unknown",
            "armed": False,
            "capturing": False,
            "photoCount": photo_count,
            "lastPhoto": last_photo,
            "lastTrigger": last_trigger_kind,
            "lastError": "",
            "sessionId": str(read_json(SESSION_PATH).get("id", "")),
            "camera": load_config()["camera"],
            "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
