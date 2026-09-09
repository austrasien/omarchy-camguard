# CamGuard for Omarchy

CamGuard is an Omarchy bar plugin that photographs activity at a locked
laptop. It watches for a lid opening, pointer movement, trackpad activity, or
a key press, without recording keys, coordinates, or raw input events.

## Behavior

When Omarchy is locked, the first activity captures one photo immediately.
Further activity resets two follow-up captures for 5 and 10 seconds later.
Capture stops on unlock.

On unlock, CamGuard removes the last three photos from that lock session. If
the session produced photos and images still remain, Omarchy displays a
critical notification. Images older than 24 hours are removed automatically.

The panel shows the three newest images from the last five minutes, opens an
image in the default viewer, and can delete all stored photos.

## Requirements

- Omarchy 4.0.3 or newer
- Python 3.11 or newer
- `ffmpeg`, `libnotify`, `polkit`, and systemd
- A V4L2 camera (default: `/dev/video0`)
- Linux input event devices and the system `input` group

The installer requires administrator approval because the daemon needs
read-only access to `/dev/input/event*`. It does not modify UWSM environment
files or the Omarchy lock plugin.

## Install

```bash
omarchy plugin add https://github.com/austrasien/omarchy-camguard.git --enable
cd ~/.config/omarchy/plugins/austraz.camguard
./install.sh
```

The plugin installs:

- the daemon at `/usr/local/libexec/omarchy-camguard-daemon`;
- its hardened system service at
  `/etc/systemd/system/omarchy-camguard.service`;
- the controller at `~/.local/bin/omarchy-camguardctl`;
- configuration under `~/.config/omarchy-camguard/`.

The install script detects the current user, primary group, UID, and home
directory. Existing configuration and photos are preserved on updates. Run it
from an unlocked session; it restarts Omarchy Shell to load the lock bridge
cleanly.

## Update

```bash
omarchy plugin update austraz.camguard --yes
cd ~/.config/omarchy/plugins/austraz.camguard
./install.sh
```

## Configure

Edit `~/.config/omarchy-camguard/config.json`:

```json
{
  "camera": "/dev/video0",
  "enabled": true,
  "intervalSeconds": 5,
  "resolution": "1280x720",
  "retentionSeconds": 86400
}
```

`photoDirectory` may be added to select another directory. If omitted, it is
`~/Pictures/CamGuard`.

Apply configuration changes automatically by saving the file. Useful commands:

```bash
omarchy-camguardctl status
omarchy-camguardctl enable
omarchy-camguardctl disable
omarchy-camguardctl open
omarchy-camguardctl delete
```

## Uninstall

```bash
cd ~/.config/omarchy/plugins/austraz.camguard
./uninstall.sh
omarchy plugin remove austraz.camguard
```

Uninstalling preserves `~/Pictures/CamGuard` and
`~/.config/omarchy-camguard`. Remove those manually if they are no longer
needed.

## Troubleshooting

```bash
systemctl status omarchy-camguard.service
journalctl -u omarchy-camguard.service --since today
omarchy-camguardctl status
omarchy-shell lock isLocked
```

If the status reports `lockState: "unknown"`, restart the shell with
`omarchy restart shell` and check that the plugin is enabled.

The camera privacy LED is hardware-controlled on most laptops and cannot be
disabled by CamGuard.

## Security and privacy

See [SECURITY.md](SECURITY.md) for the permission model, stored data, and
responsible disclosure guidance.

## License

MIT
