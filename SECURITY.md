# Security and privacy

CamGuard is security-sensitive software. It can read selected Linux input
event devices and activate the camera while the Omarchy session is locked.

## Data collected

CamGuard stores PNG images in `~/Pictures/CamGuard` by default. Files are
created with mode `0600`. Session metadata and daemon status are stored under
`~/.local/state/omarchy-camguard`, also with private permissions.

Input events are used only to classify activity as lid, keyboard, trackpad, or
mouse. Key codes, typed text, pointer coordinates, and raw events are not
written to disk or logs.

Images older than the configured retention period (24 hours by default) are
deleted every five minutes while the daemon runs. Secure deletion cannot be
guaranteed on SSDs, copy-on-write filesystems, snapshots, or backups.

## Permission model

The root-assisted installer:

- installs a root-owned daemon executable and systemd unit;
- runs the daemon as the selected desktop user, never as root;
- grants the process supplemental membership in the `input` group;
- restricts filesystem writes to the photo and state directories;
- removes Linux capabilities and blocks network access except local Unix
  sockets used for desktop notifications.

Review `install-system.sh` and `omarchy-camguard.service` before approving the
Polkit prompt.

## Lock-state boundary

Omarchy 4.0.3 isolates authentication services from third-party plugins.
CamGuard does not access password, fingerprint, PAM, or lock-service objects.
Its QML service reads Hyprland's monitor metadata using the same
`solitaryBlockedBy: LOCK` signal as Omarchy's
`omarchy hyprland session locked` command, then publishes only a boolean state
to the daemon.

If lock state is missing or invalid, the daemon uses `unknown` and does not
arm the camera.

## Reporting vulnerabilities

Please report vulnerabilities privately through GitHub Security Advisories
for the repository. Do not include captured photos, credentials, or personal
paths in a public issue.
