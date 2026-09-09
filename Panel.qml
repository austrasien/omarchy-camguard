import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root

  moduleName: "austraz.camguard"
  ipcTarget: "austraz.camguard"
  manageIpc: false

  readonly property string ctl: (Quickshell.env("HOME") || "") + "/.local/bin/omarchy-camguardctl"
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.5)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  property bool serviceActive: false
  property bool enabled: true
  property bool locked: false
  property bool armed: false
  property bool capturing: false
  property int photoCount: 0
  property string lastPhoto: ""
  property string lastTrigger: ""
  property real lastTriggerAt: 0
  property string lastError: ""
  property string updatedAt: ""
  property var recentPhotos: []
  property real nowSeconds: Date.now() / 1000
  readonly property bool hasRecentPhotos: recentPhotos.length > 0

  readonly property string stateTitle: {
    if (!serviceActive) return "Service unavailable"
    if (!enabled) return "Disabled"
    if (capturing) return "Capturing"
    if (armed) return "Watching for activity"
    return "Waiting for lock"
  }

  readonly property string stateDetail: {
    if (!serviceActive) return "Install or restart omarchy-camguard.service"
    if (!enabled) return "Monitoring is paused"
    if (capturing) return "First photo immediate · activity resets +5s and +10s"
    if (armed) return "Lid open · pointer movement · keyboard press"
    return "Monitoring starts on the next lock"
  }

  function triggerLabel(value) {
    if (value === "lid") return "Lid opened"
    if (value === "trackpad") return "Trackpad"
    if (value === "mouse") return "Mouse"
    if (value === "keyboard") return "Keyboard"
    return "—"
  }

  function relativeTime(timestamp) {
    var seconds = Math.max(0, Math.floor(root.nowSeconds - Number(timestamp || 0)))
    if (!(timestamp > 0)) return ""
    if (seconds < 10) return "just now"
    if (seconds < 60) return seconds + " secs ago"
    var minutes = Math.floor(seconds / 60)
    if (minutes < 60) return minutes + (minutes === 1 ? " min ago" : " mins ago")
    var hours = Math.floor(minutes / 60)
    if (hours < 24) return hours + (hours === 1 ? " hr ago" : " hrs ago")
    var days = Math.floor(hours / 24)
    return days + (days === 1 ? " day ago" : " days ago")
  }

  function triggerSummary() {
    var label = root.triggerLabel(root.lastTrigger)
    var relative = root.relativeTime(root.lastTriggerAt)
    return relative === "" ? label : label + " · " + relative
  }

  function photoLabel(path) {
    if (!path) return "—"
    var parts = String(path).split("/")
    return parts[parts.length - 1]
  }

  function applyStatus(raw) {
    try {
      var value = JSON.parse(String(raw || "{}"))
      serviceActive = value.serviceActive === true
      enabled = value.enabled !== false
      locked = value.locked === true
      armed = value.armed === true
      capturing = value.capturing === true
      photoCount = Number(value.photoCount || 0)
      lastPhoto = String(value.lastPhoto || "")
      lastTrigger = String(value.lastTrigger || "")
      lastTriggerAt = Number(value.lastTriggerAt || 0)
      lastError = String(value.lastError || "")
      updatedAt = String(value.updatedAt || "")
      recentPhotos = Array.isArray(value.recentPhotos) ? value.recentPhotos : []
    } catch (error) {
      serviceActive = false
      lastError = "Invalid service status"
    }
  }

  function refresh() {
    if (!statusProc.running) statusProc.running = true
  }

  function toggleEnabled() {
    if (actionProc.running) return
    actionProc.command = [root.ctl, "toggle"]
    actionProc.running = true
  }

  function openPhotos() {
    Quickshell.execDetached([root.ctl, "open"])
  }

  function revealPhoto(path) {
    Quickshell.execDetached([root.ctl, "reveal", String(path)])
  }

  function deletePhotos() {
    if (actionProc.running) return
    actionProc.command = [root.ctl, "delete"]
    actionProc.running = true
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onOpenedChanged: if (opened) {
    root.refresh()
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): string { root.refresh(); return "ok" }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰄀"
    active: root.capturing
    foreground: root.hasRecentPhotos ? "#ffffff" : root.foreground
    useActiveColor: !root.hasRecentPhotos
    opacity: root.hasRecentPhotos || (root.enabled && root.serviceActive) ? 1.0 : 0.45
    tooltipText: "CamGuard · " + root.stateTitle

    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) root.toggleEnabled()
      else if (buttonCode === Qt.MiddleButton) root.openPhotos()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(content.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onActivateRequested: root.toggleEnabled()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(text) {
        if (text === "o" || text === "O") root.openPhotos()
        else if (text === "r" || text === "R") root.refresh()
      }

      Column {
        id: content
        width: parent.width
        spacing: Style.space(12)

        PanelHero {
          width: parent.width
          title: root.stateTitle
          meta: root.stateDetail
          foreground: root.foreground
          fontFamily: root.fontFamily

          iconComponent: Component {
            Text {
              text: "󰄀"
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.display
            }
          }
        }

        PanelSeparator {
          foreground: root.foreground
        }

        Column {
          visible: root.hasRecentPhotos
          width: parent.width
          spacing: Style.space(8)

          PanelSectionHeader {
            width: parent.width
            text: "RECENT PHOTOS · LAST 5 MINUTES"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Row {
            id: recentGallery
            width: parent.width
            spacing: Style.space(6)

            Repeater {
              model: root.recentPhotos

              Rectangle {
                required property var modelData
                required property int index

                width: (recentGallery.width - recentGallery.spacing * 2) / 3
                height: Math.round(width * 9 / 16)
                radius: Style.cornerRadius
                clip: true
                color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.08)
                border.width: 1
                border.color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.22)

                Image {
                  anchors.fill: parent
                  source: Util.fileUrl(String(parent.modelData))
                  fillMode: Image.PreserveAspectCrop
                  asynchronous: true
                  cache: false
                  smooth: true
                }

                MouseArea {
                  anchors.fill: parent
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.revealPhoto(parent.modelData)
                }
              }
            }
          }
        }

        Grid {
          width: parent.width
          columns: 2
          columnSpacing: Style.space(20)
          rowSpacing: Style.space(8)

          Text {
            text: "Last trigger"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }
          Text {
            width: content.width / 2 - Style.space(10)
            text: root.triggerSummary()
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            horizontalAlignment: Text.AlignRight
            elide: Text.ElideLeft
          }

          Text {
            text: "Last photo"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }
          Text {
            width: content.width / 2 - Style.space(10)
            text: root.photoLabel(root.lastPhoto)
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            horizontalAlignment: Text.AlignRight
            elide: Text.ElideLeft
          }

          Text {
            text: "Stored photos"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
          }
          Text {
            width: content.width / 2 - Style.space(10)
            text: String(root.photoCount)
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            horizontalAlignment: Text.AlignRight
          }
        }

        Text {
          visible: root.lastError !== ""
          width: parent.width
          text: root.lastError
          color: root.urgent
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }

        Row {
          width: parent.width
          spacing: Style.space(8)

          Button {
            width: (parent.width - parent.spacing) / 2
            text: root.enabled ? "Disable" : "Enable"
            foreground: root.foreground
            fontFamily: root.fontFamily
            bordered: true
            onClicked: root.toggleEnabled()
          }

          Button {
            width: (parent.width - parent.spacing) / 2
            text: "Open photos"
            foreground: root.foreground
            fontFamily: root.fontFamily
            bordered: true
            onClicked: root.openPhotos()
          }
        }

        Button {
          width: parent.width
          text: "Delete photos"
          enabled: root.photoCount > 0
          foreground: root.urgent
          fontFamily: root.fontFamily
          bordered: true
          onClicked: root.deletePhotos()
        }

        Text {
          width: parent.width
          text: "Photos are automatically deleted after 24 hours."
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          horizontalAlignment: Text.AlignHCenter
          wrapMode: Text.WordWrap
        }
      }
    }
  }

  Timer {
    interval: root.opened || root.capturing ? 1000 : 3000
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: {
      root.nowSeconds = Date.now() / 1000
      root.refresh()
    }
  }

  Process {
    id: statusProc
    command: [root.ctl, "status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applyStatus(text)
    }
  }

  Process {
    id: actionProc
    onExited: {
      root.refresh()
    }
  }
}
