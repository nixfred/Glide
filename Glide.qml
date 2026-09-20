import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "nixfred.glide"
  ipcTarget: "nixfred.glide"
  property var state: ({running: false, ready: false, connected: false})
  property var inventory: ({self: {}, devices: [], layout: {machines: []}, lan: []})
  property var draft: []
  property string selected: ""
  property bool dirty: false
  property string message: ""
  property bool failed: false
  readonly property string helper: Qt.resolvedUrl("scripts/glide-control.py").toString().replace(/^file:\/\//, "")
  readonly property string networkHelper: Qt.resolvedUrl("scripts/network.py").toString().replace(/^file:\/\//, "")
  readonly property bool busy: apply.running || control.running
  readonly property string statusText: state.error ? "Needs attention" : !state.running ? "Paused" : state.connected ? "Connected" : state.ready ? "Ready to glide" : "Ready"
  readonly property var selectedMachine: draft.find(function(n) { return n.id === root.selected }) || inventory.devices.find(function(n) { return n.id === root.selected }) || null
  readonly property bool selectedInLayout: draft.some(function(n) { return n.id === root.selected })
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function refresh() { if (!poll.running) poll.running = true }
  function scan() { if (!scanProcess.running && !apply.running) scanProcess.running = true }
  function reloadDraft() {
    draft = JSON.parse(JSON.stringify(inventory.layout.machines))
    dirty = false
    message = ""
  }
  function act(action) {
    if (busy) return
    control.command = ["python3", helper, action]
    control.running = true
  }
  function moveMachine(index, x, y) {
    if (busy) return
    x = Math.max(-2, Math.min(2, x)); y = Math.max(-1, Math.min(1, y))
    var updated = JSON.parse(JSON.stringify(draft))
    if (updated.some(function(n, i) { return i !== index && n.x === x && n.y === y })) {
      draft = updated; message = "Choose an empty position."; failed = true; return
    }
    updated[index].x = x; updated[index].y = y
    draft = updated; dirty = true; message = "Layout changed. Apply to update every machine."; failed = false
  }
  function nudge(dx, dy) {
    var i = draft.findIndex(function(n) { return n.id === root.selected })
    if (i >= 0) moveMachine(i, draft[i].x + dx, draft[i].y + dy)
  }
  function addSelected() {
    if (!selectedMachine || selectedInLayout || draft.length >= 9 || busy) return
    var n = Object.assign({}, selectedMachine)
    var spots = [[-1,0],[1,0],[0,-1],[0,1],[-2,0],[2,0],[-1,-1],[1,-1],[-1,1],[1,1],[-2,-1],[2,-1],[-2,1],[2,1]]
    for (var i=0; i<spots.length; i++) {
      var x=spots[i][0], y=spots[i][1]
      if (!draft.some(function(p) { return p.x===x && p.y===y })) {
        n.x=x; n.y=y; draft=draft.concat([n]); dirty=true; message="Drag the machine into place, then Apply."; failed=false; return
      }
    }
  }
  function removeSelected() {
    if (selected === inventory.self.id || busy) return
    draft = draft.filter(function(n) { return n.id !== root.selected })
    dirty = true; message = "Apply to remove this machine and revoke its old neighbors."; failed = false
  }
  function authorize() {
    if (!selectedMachine || selected === inventory.self.id) return
    Quickshell.execDetached(["xdg-terminal-exec", "--", "python3", networkHelper, "authorize", selected])
  }
  function saveLayout() {
    if (busy || !dirty) return
    message = "Checking SSH identities and updating the layout…"; failed = false
    apply.payload = JSON.stringify({version:1,machines:draft})
    apply.stdinEnabled = true
    apply.running = true
  }
  onOpenedChanged: if (opened) { refresh(); scan() }

  Process {
    id: poll
    command: ["python3", root.helper, "status"]
    stdout: StdioCollector { onStreamFinished: { try { root.state = JSON.parse(text) } catch(e) {} } }
  }
  Process { id: control; onExited: function(code) { root.refresh(); if (code !== 0) { root.message="Sharing action failed."; root.failed=true } } }
  Process {
    id: scanProcess
    command: ["python3", root.networkHelper, "inventory"]
    stdout: StdioCollector { onStreamFinished: {
      try {
        var response = JSON.parse(text)
        if (!response.ok) { root.message=response.error; root.failed=true; return }
        root.inventory = response.result
        if (!root.dirty) root.draft = JSON.parse(JSON.stringify(response.result.layout.machines))
        if (!root.selected) root.selected=response.result.self.id
      } catch(e) { root.message="Could not read LAN discovery."; root.failed=true }
    } }
  }
  Process {
    id: apply
    property string payload: ""
    command: ["python3", root.networkHelper, "deploy"]
    onStarted: { write(payload + "\n"); stdinEnabled = false }
    stdout: StdioCollector { onStreamFinished: {
      try {
        var response=JSON.parse(text)
        if (response.ok) { root.dirty=false; root.message="Layout applied to every machine."; root.failed=false }
        else { root.message=response.error; root.failed=true }
      } catch(e) { root.message="Layout update failed. The saved layout is unchanged."; root.failed=true }
    } }
    onExited: { root.scan(); root.refresh() }
  }
  Timer { interval: 2000; repeat: true; running: true; triggeredOnStart: true; onTriggered: root.refresh() }
  Timer { interval: 5000; repeat: true; running: root.opened; onTriggered: root.scan() }
  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰍽"
    dimmed: !root.state.running
    tooltipText: "Glide · " + root.statusText + "\nLAN mouse and keyboard sharing\nRight-click to pause or resume"
    onPressed: function(b) { if (b === Qt.RightButton) root.act("toggle"); else root.toggle() }
  }

  component Label: Text {
    textFormat: Text.PlainText
    color: Color.foreground
    font.family: Style.font.family
    font.pixelSize: Style.font.body
    wrapMode: Text.WordWrap
  }
  component Action: Button { focusable: true; bordered: true }

  KeyboardPanel {
    id: popup
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: content
    contentWidth: fittedContentWidth(Style.space(940))
    contentHeight: fittedContentHeight(content.implicitHeight)
    ColumnLayout {
      id: content
      width: parent.width
      spacing: Style.space(12)
      focus: true
      Keys.onEscapePressed: root.close()
      Keys.onLeftPressed: root.nudge(-1,0)
      Keys.onRightPressed: root.nudge(1,0)
      Keys.onUpPressed: root.nudge(0,-1)
      Keys.onDownPressed: root.nudge(0,1)
      RowLayout {
        Layout.fillWidth: true
        Label { text: "Glide"; font.pixelSize: Style.font.title; font.bold: true }
        Label { text: "Mouse owner wins"; color: Color.accent }
        Item { Layout.fillWidth: true }
        Label { text: root.statusText; color: root.state.ready ? Color.accent : Color.foreground }
        Action { text: root.state.running ? "Pause" : "Resume"; enabled: !root.busy; onClicked: root.act("toggle") }
      }
      Label { Layout.fillWidth: true; text: "Drag machines to match your desk. Cross an edge to share your keyboard and mouse; move another machine’s own mouse to take control there." }
      Item {
        id: board
        Layout.fillWidth: true
        implicitHeight: Style.space(228)
        readonly property real cellWidth: width / 5
        readonly property real cellHeight: height / 3
        Repeater {
          model: 15
          Rectangle {
            required property int index
            x: (index % 5) * board.cellWidth + 3
            y: Math.floor(index / 5) * board.cellHeight + 3
            width: board.cellWidth-6; height: board.cellHeight-6
            radius: Style.space(6)
            color: Qt.alpha(Color.foreground, 0.025)
            border.color: Qt.alpha(Color.foreground, 0.12)
            Label { anchors.centerIn: parent; text: "+"; color: Qt.alpha(Color.foreground,0.22) }
          }
        }
        Repeater {
          model: root.draft
          Rectangle {
            id: machineCard
            required property var modelData
            required property int index
            objectName: "glide-machine-"+modelData.name
            x: (modelData.x+2)*board.cellWidth+6
            y: (modelData.y+1)*board.cellHeight+6
            width: board.cellWidth-12; height: board.cellHeight-12
            z: dragArea.drag.active ? 10 : 1
            radius: Style.space(6)
            color: root.selected===modelData.id ? Qt.alpha(Color.accent,0.24) : Color.background
            border.color: root.selected===modelData.id ? Color.accent : Qt.alpha(Color.accent,0.45)
            border.width: root.selected===modelData.id ? 2 : 1
            Column {
              anchors.centerIn: parent
              width: parent.width-Style.space(10)
              spacing: Style.space(3)
              Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: machineCard.modelData.name; font.bold: true }
              Label { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: machineCard.modelData.id===root.inventory.self.id ? "This machine" : machineCard.modelData.ip; font.pixelSize: Style.font.caption; color: Qt.alpha(Color.foreground,0.7) }
            }
            MouseArea {
              id: dragArea
              anchors.fill: parent
              enabled: !root.busy
              cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
              drag.target: machineCard
              drag.minimumX: 0; drag.maximumX: board.width-machineCard.width
              drag.minimumY: 0; drag.maximumY: board.height-machineCard.height
              onPressed: { root.selected=machineCard.modelData.id; content.forceActiveFocus() }
              onReleased: root.moveMachine(machineCard.index, Math.round((machineCard.x-6)/board.cellWidth)-2, Math.round((machineCard.y-6)/board.cellHeight)-1)
            }
          }
        }
      }
      RowLayout {
        Layout.fillWidth: true
        Label { text: root.selectedMachine ? root.selectedMachine.name : "Select a machine"; font.bold: true; Layout.minimumWidth: Style.space(75) }
        Action { text: "←"; enabled: root.selectedInLayout && !root.busy; onClicked: root.nudge(-1,0) }
        Action { text: "↑"; enabled: root.selectedInLayout && !root.busy; onClicked: root.nudge(0,-1) }
        Action { text: "↓"; enabled: root.selectedInLayout && !root.busy; onClicked: root.nudge(0,1) }
        Action { text: "→"; enabled: root.selectedInLayout && !root.busy; onClicked: root.nudge(1,0) }
        Item { Layout.fillWidth: true }
        Action { text: "Authorize SSH"; enabled: !!root.selectedMachine && root.selected!==root.inventory.self.id && !root.busy; onClicked: root.authorize() }
        Action { text: "Remove"; enabled: root.selectedInLayout && root.selected!==root.inventory.self.id && !root.busy; onClicked: root.removeSelected() }
      }
      RowLayout {
        Layout.fillWidth: true
        Label { text: "Nearby Omarchy machines"; font.bold: true }
        Label { text: "LAN only · active sessions"; color: Qt.alpha(Color.foreground,0.6) }
        Item { Layout.fillWidth: true }
        Action { text: scanProcess.running ? "Scanning…" : "Scan LAN"; enabled: !scanProcess.running && !root.busy; onClicked: root.scan() }
      }
      Flow {
        id: nearby
        Layout.fillWidth: true
        implicitHeight: childrenRect.height
        spacing: Style.space(6)
        Repeater {
          model: root.inventory.devices
          Action {
            required property var modelData
            text: modelData.name + " · " + modelData.ip
            selected: root.selected===modelData.id
            onClicked: root.selected=modelData.id
          }
        }
        Label { visible: root.inventory.devices.length===0; text: "No other active Glide sessions found. Install Glide and log in on each machine." }
      }
      RowLayout {
        Layout.fillWidth: true
        Label { Layout.fillWidth: true; text: "Pairing uses your SSH login. Discovery alone never grants control.\nEmergency return: left Ctrl + left Shift + Esc. Clipboard stays local."; color: Qt.alpha(Color.foreground,0.7); font.pixelSize: Style.font.caption }
        Action { text: "Add selected"; enabled: !!root.selectedMachine && !root.selectedInLayout && root.draft.length<9 && !root.busy; onClicked: root.addSelected() }
      }
      Label {
        visible: root.message!==""; Layout.fillWidth: true
        text: root.message; color: root.failed ? Color.urgent : Color.accent
        font.pixelSize: Style.font.caption
      }
      RowLayout {
        Layout.fillWidth: true
        Label { text: root.draft.length+" / 9 machines"; color: Qt.alpha(Color.foreground,0.6) }
        Item { Layout.fillWidth: true }
        Action { text: "Reset draft"; enabled: root.dirty && !root.busy; onClicked: root.reloadDraft() }
        Action { text: apply.running ? "Applying…" : "Apply layout"; enabled: root.dirty && !root.busy; onClicked: root.saveLayout() }
        Action { text: "Close"; enabled: !apply.running; onClicked: root.close() }
      }
    }
  }
}
