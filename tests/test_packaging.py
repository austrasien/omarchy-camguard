#!/usr/bin/env python3

import json
import os
import unittest
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_manifest_entry_points_exist(self) -> None:
        manifest = json.loads((PLUGIN_DIR / "manifest.json").read_text())
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["version"], "1.1.0")
        for entry_point in manifest["entryPoints"].values():
            self.assertTrue((PLUGIN_DIR / entry_point).is_file())

    def test_required_release_files_exist(self) -> None:
        for relative in (
            "README.md",
            "SECURITY.md",
            "LICENSE",
            "CHANGELOG.md",
            "config.example.json",
            "bin/omarchy-camguardctl",
            "install.sh",
            "install-system.sh",
            "uninstall.sh",
            "uninstall-system.sh",
        ):
            self.assertTrue((PLUGIN_DIR / relative).is_file(), relative)

    def test_scripts_are_executable(self) -> None:
        for relative in (
            "bin/omarchy-camguardctl",
            "install.sh",
            "install-system.sh",
            "uninstall.sh",
            "uninstall-system.sh",
        ):
            self.assertTrue(os.access(PLUGIN_DIR / relative, os.X_OK), relative)

    def test_release_has_no_machine_specific_paths(self) -> None:
        forbidden = (
            "/home/" + "austraz",
            "User=" + "austraz",
            "/run/user/" + "1000",
            "austraz" + ".lock",
        )
        checked_suffixes = {".py", ".qml", ".sh", ".service", ".json", ".md"}
        for path in PLUGIN_DIR.rglob("*"):
            if not path.is_file() or path.suffix not in checked_suffixes:
                continue
            if "__pycache__" in path.parts or path == Path(__file__):
                continue
            text = path.read_text(encoding="utf-8")
            for value in forbidden:
                self.assertNotIn(value, text, f"{value!r} found in {path}")

    def test_service_template_is_fully_renderable(self) -> None:
        text = (PLUGIN_DIR / "omarchy-camguard.service").read_text()
        values = {
            "@USER@": "example",
            "@GROUP@": "example",
            "@UID@": "1234",
            "@HOME@": "/home/example",
        }
        for marker, value in values.items():
            text = text.replace(marker, value)
        self.assertNotIn("@", text)
        self.assertIn("User=example", text)
        self.assertIn("Environment=XDG_RUNTIME_DIR=/run/user/1234", text)

    def test_lock_bridge_uses_compositor_state_only(self) -> None:
        text = (PLUGIN_DIR / "Service.qml").read_text()
        self.assertIn('command: ["hyprctl", "-j", "monitors"]', text)
        self.assertIn('blockers.indexOf("LOCK")', text)
        self.assertNotIn("serviceFor(", text)


if __name__ == "__main__":
    unittest.main()
