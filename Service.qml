import QtQuick
import Quickshell
import Quickshell.Io

Item {
  id: root

  property var shell: null
  property string lastPublished: ""
  property int pollIntervalMs: 1000

  readonly property string ctl:
    (Quickshell.env("HOME") || "") + "/.local/bin/omarchy-camguardctl"

  function probeLockState() {
    if (!lockProbe.running) lockProbe.running = true
  }

  function stateFromMonitors(raw) {
    try {
      var monitors = JSON.parse(String(raw || "[]"))
      if (!Array.isArray(monitors)) return ""
      var hasReadableMonitor = false
      for (var i = 0; i < monitors.length; i++) {
        var blockers = Array.isArray(monitors[i].solitaryBlockedBy)
          ? monitors[i].solitaryBlockedBy : []
        if (blockers.indexOf("LOCK") !== -1) return "true"
        if (blockers.indexOf("WORKSPACE") === -1) hasReadableMonitor = true
      }
      return hasReadableMonitor ? "false" : ""
    } catch (error) {
      return ""
    }
  }

  function publish(value) {
    if (value !== "true" && value !== "false") return
    root.pollIntervalMs = value === "true" ? 500 : 1000
    if (value === root.lastPublished) return
    root.lastPublished = value
    Quickshell.execDetached([root.ctl, "lock-state", value])
  }

  Process {
    id: lockProbe
    command: ["hyprctl", "-j", "monitors"]
    stdout: StdioCollector {
      id: lockProbeOutput
      waitForEnd: true
    }
    onExited: function(exitCode) {
      var value = exitCode === 0
        ? root.stateFromMonitors(lockProbeOutput.text) : ""
      if (value !== "") {
        root.publish(value)
      } else {
        // Outputs may still be starting. Back off until state is readable.
        root.pollIntervalMs = 2000
      }
    }
  }

  Timer {
    interval: root.pollIntervalMs
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: root.probeLockState()
  }
}
