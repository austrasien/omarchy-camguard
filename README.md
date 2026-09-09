# CamGuard for Omarchy

An **Omarchy bar plugin** that photographs activity on a **locked** laptop: lid open, pointer movement, trackpad touch, or a key press — without recording keys, coordinates, or raw input events.

> **⚡ Built for Omarchy 4.0.3+:** lock detection uses Hyprland compositor state (same signal as `omarchy hyprland session locked`). No custom lock-plugin patch, no access to PAM / fingerprint / password objects.

```
Locked session  →  lid / pointer / keyboard trigger  →  photo burst  →  unlock cleanup + optional alert
```

---

### ☕ Support the Project
If CamGuard catches something you would rather have on disk than wonder about later, a tip is always appreciated.

[![Donate via PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg?style=for-the-badge&logo=paypal)](https://paypal.me/austraz)

---

### 💬 Feedback & Community
Got a question, found a bug, or have a suggestion? Open an [**issue**](https://github.com/austrasien/omarchy-camguard/issues).

---

## 🚀 Overview

When Omarchy is locked, CamGuard arms a small privileged daemon. The first activity captures one photo immediately; further activity resets two follow-up captures at +5 s and +10 s. Capture stops on unlock.

| | Without ❌ | With CamGuard ✅ |
| :--- | :--- | :--- |
| **Someone opens the lid** | You unlock later with no trail | Photos under `~/Pictures/CamGuard` |
| **Typing / trackpad while locked** | Same | Burst capped to a short activity window |
| **Your own unlock** | — | Last 3 session photos removed so routine unlocks stay quiet |
| **Intruder left more evidence** | Easy to miss | Critical Omarchy notification if photos remain |
| **Old captures** | Manual cleanup | Auto-delete after 24 h (configurable) |

> **Note:** The camera privacy LED is hardware-controlled on most laptops. CamGuard cannot hide it.

## ✨ Key Features

### 📸 Locked-session capture
- Triggers: lid open, mouse / trackpad motion, keyboard press.
- First shot immediate; activity resets the +5 s / +10 s schedule.
- Atomic PNG writes; images mode `0600`.

### 🧹 Unlock hygiene
- Deletes only the last three photos from the **current** lock session.
- If that session produced photos and files still remain → critical `notify-send` popup.
- Retention sweep every five minutes while the daemon runs.

### 🧩 Omarchy bar panel
- Icon turns white when photos from the last five minutes exist.
- Gallery of up to three recent shots; click opens the image (no file-manager detour).
- Enable / disable, open folder, delete all photos.
- Reminder text: photos older than 24 hours are removed automatically.

### 🛡 Hardened daemon
- Systemd unit runs as **your** user (never root), with `input` group for `/dev/input/event*`.
- No network except Unix sockets (notifications); home mostly read-only; writes limited to photo + state dirs.
- Portable installer: detects user / UID / home, preserves config on updates, non-destructive uninstall.

## 🛠 Installation (Omarchy)

**Requirements:** Omarchy 4.0.3+, Python 3.11+, `ffmpeg`, `libnotify`, `polkit`, a V4L2 camera (`/dev/video0` by default), Linux input devices.

1. **Add the plugin and install the daemon** (unlocked session):

   ```sh
   omarchy plugin add https://github.com/austrasien/omarchy-camguard.git --enable
   cd ~/.config/omarchy/plugins/austraz.camguard
   ./install.sh
   ```

   `install.sh` asks for administrator approval via Polkit, installs the daemon + systemd unit + `~/.local/bin/omarchy-camguardctl`, then restarts Omarchy Shell so the lock bridge loads cleanly.

2. **Useful commands:**

   ```sh
   omarchy-camguardctl status
   omarchy-camguardctl enable
   omarchy-camguardctl disable
   omarchy-camguardctl open
   omarchy-camguardctl delete
   ```

### Update

```sh
omarchy plugin update austraz.camguard --yes
cd ~/.config/omarchy/plugins/austraz.camguard
./install.sh
```

Existing configuration and photos are preserved.

### Configure

Edit `~/.config/omarchy-camguard/config.json` (created on first install):

```json
{
  "camera": "/dev/video0",
  "enabled": true,
  "intervalSeconds": 5,
  "resolution": "1280x720",
  "retentionSeconds": 86400
}
```

Optional: `"photoDirectory": "/path/to/folder"`. Default is `~/Pictures/CamGuard`. Save the file; the daemon reloads it.

### Uninstall

```sh
cd ~/.config/omarchy/plugins/austraz.camguard
./uninstall.sh
omarchy plugin remove austraz.camguard
```

Photos and `~/.config/omarchy-camguard` are kept; remove them manually if you want.

## 🩺 Troubleshooting

```sh
systemctl status omarchy-camguard.service
journalctl -u omarchy-camguard.service --since today
omarchy-camguardctl status
```

If status shows `lockState: "unknown"`, run `omarchy restart shell` from an unlocked session and confirm the plugin is enabled.

## 🔐 Security and privacy

See [SECURITY.md](SECURITY.md). Short version:

- Key codes, typed text, and pointer coordinates are **never** logged or written to disk.
- Lock state is a boolean published from Hyprland monitor metadata — not from the authentication service.
- The installer does **not** touch `~/.config/uwsm/env.d/` or patch the Omarchy lock plugin.

## ⚖️ License

Licensed under the **MIT License**. Permissive for both personal and commercial use, provided attribution is maintained.

---
*Developed so a locked Omarchy laptop leaves a trail when someone else wakes it — without babysitting the camera.*
