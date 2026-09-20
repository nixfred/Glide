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
  property real animationPhase: 0
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
    if (updated[index].x===x && updated[index].y===y) { draft=updated; return }
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

  IpcHandler {
    target: "glide-layout"
    function inspect(): string {
      return JSON.stringify({draft:root.draft, saved:root.inventory.layout, selected:root.selected,
        dirty:root.dirty, busy:root.busy, message:root.message, failed:root.failed,
        panelWidth:popup.contentWidth, panelHeight:popup.contentHeight,
        contentHeight:content.implicitHeight, availableHeight:popup.availableCardHeight})
    }
    function selectMachine(id: string): void { root.selected=id }
    function moveSelected(dx: int, dy: int): void { root.nudge(dx,dy) }
    function applyLayout(): void { root.saveLayout() }
    function resetDraft(): void { root.reloadDraft() }
  }
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
  Timer { interval: 40; repeat: true; running: root.opened && root.state.running; onTriggered: { root.animationPhase = (root.animationPhase + 0.012) % 1; circuitry.requestPaint() } }
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
      Rectangle {
        Layout.fillWidth: true
        implicitHeight: Style.space(80)
        radius: Style.space(10)
        color: Qt.alpha(Color.accent, 0.075)
        border.color: Qt.alpha(Color.accent, 0.22)
        RowLayout {
          anchors.fill: parent
          anchors.margins: Style.space(14)
          spacing: Style.space(16)
          Item {
            Layout.preferredWidth: Style.space(92)
            Layout.fillHeight: true
            Repeater {
              model: 3
              Rectangle {
                required property int index
                x: Style.space(index * 24 + 2)
                y: Style.space(index === 1 ? 0 : 12)
                width: Style.space(35); height: Style.space(26)
                radius: Style.space(4)
                color: Color.background
                border.color: Color.accent
                border.width: index===1 ? 2 : 1
                Rectangle { anchors.fill: parent; anchors.margins: 4; radius: 2; color: Qt.alpha(Color.accent,0.15+parent.index*0.06) }
                Rectangle { anchors.top: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; width: Style.space(2); height: Style.space(5); color: Color.accent }
                Rectangle { anchors.top: parent.bottom; anchors.topMargin: Style.space(5); anchors.horizontalCenter: parent.horizontalCenter; width: Style.space(16); height: Style.space(2); color: Color.accent }
              }
            }
          }
          Column {
            spacing: Style.space(3)
            Label { text: "GLIDE"; font.pixelSize: Style.space(27); font.bold: true; font.letterSpacing: Style.space(5) }
            Label { text: "ONE DESK. EVERY MACHINE."; color: Color.accent; font.pixelSize: Style.font.caption; font.letterSpacing: Style.space(1) }
          }
          Item { Layout.fillWidth: true }
          Column {
            spacing: Style.space(5)
            Label { text: root.statusText.toUpperCase(); color: root.state.ready ? Color.accent : Color.foreground; font.bold: true; horizontalAlignment: Text.AlignRight; anchors.right: parent.right }
            Label { text: "LAN ONLY  /  ENCRYPTED"; color: Qt.alpha(Color.foreground,0.55); font.pixelSize: Style.font.caption }
          }
          Action { text: root.state.running ? "Pause" : "Resume"; enabled: !root.busy; onClicked: root.act("toggle") }
        }
      }
      Label { Layout.fillWidth: true; text: "Drag machines to match your desk. Cross an edge to share your keyboard and mouse; use another machine’s own mouse or keyboard to take control there." }
      Item {
        id: board
        Layout.fillWidth: true
        implicitHeight: Style.space(246)
        readonly property real cellWidth: width / 5
        readonly property real cellHeight: height / 3
        Rectangle {
          anchors.fill: parent
          radius: Style.space(9)
          color: Qt.alpha(Color.background, 0.65)
          border.color: Qt.alpha(Color.accent, 0.2)
        }
        Canvas {
          id: circuitry
          anchors.fill: parent
          onWidthChanged: requestPaint()
          onHeightChanged: requestPaint()
          Connections { target: root; function onDraftChanged() { circuitry.requestPaint() } }
          onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var accent = Color.accent
            ctx.fillStyle = Qt.alpha(accent, 0.18)
            for (var gx=12; gx<width; gx+=24) for (var gy=12; gy<height; gy+=24) ctx.fillRect(gx,gy,1,1)
            for (var a=0; a<root.draft.length; a++) {
              var n=root.draft[a]
              for (var b=a+1; b<root.draft.length; b++) {
                var m=root.draft[b]
                if (n.x!==m.x && n.y!==m.y) continue
                var between=root.draft.some(function(k) {
                  return n.y===m.y ? (k.y===n.y && k.x>Math.min(n.x,m.x) && k.x<Math.max(n.x,m.x)) : (k.x===n.x && k.y>Math.min(n.y,m.y) && k.y<Math.max(n.y,m.y))
                })
                if (between) continue
                var x1=(n.x+2.5)*board.cellWidth, y1=(n.y+1.5)*board.cellHeight
                var x2=(m.x+2.5)*board.cellWidth, y2=(m.y+1.5)*board.cellHeight
                var bend=n.y===m.y ? -board.cellHeight*0.72 : board.cellWidth*0.48
                var c1x=n.y===m.y ? x1 : x1+bend, c1y=n.y===m.y ? y1+bend : y1
                var c2x=n.y===m.y ? x2 : x2+bend, c2y=n.y===m.y ? y2+bend : y2
                ctx.beginPath(); ctx.moveTo(x1,y1); ctx.bezierCurveTo(c1x,c1y,c2x,c2y,x2,y2)
                ctx.lineWidth=5; ctx.strokeStyle=Qt.alpha(accent,0.10); ctx.stroke()
                ctx.lineWidth=1.5; ctx.strokeStyle=Qt.alpha(accent,root.dirty ? 0.35 : 0.7); ctx.stroke()
                if (root.state.running) {
                  var t=(root.animationPhase+a*0.17)%1, u=1-t
                  var px=u*u*u*x1+3*u*u*t*c1x+3*u*t*t*c2x+t*t*t*x2
                  var py=u*u*u*y1+3*u*u*t*c1y+3*u*t*t*c2y+t*t*t*y2
                  ctx.beginPath(); ctx.arc(px,py,5,0,Math.PI*2); ctx.fillStyle=Qt.alpha(accent,0.15); ctx.fill()
                  ctx.beginPath(); ctx.arc(px,py,2,0,Math.PI*2); ctx.fillStyle=accent; ctx.fill()
                }
              }
            }
          }
        }
        Repeater {
          model: 15
          Rectangle {
            required property int index
            x: (index % 5) * board.cellWidth + 3
            y: Math.floor(index / 5) * board.cellHeight + 3
            width: board.cellWidth-6; height: board.cellHeight-6
            radius: Style.space(6)
            color: "transparent"
            border.color: Qt.alpha(Color.foreground, 0.06)
            Label { anchors.centerIn: parent; text: "·"; color: Qt.alpha(Color.accent,0.2) }
          }
        }
        Repeater {
          model: root.draft
          Rectangle {
            id: machineCard
            required property var modelData
            required property int index
            objectName: "glide-machine-"+modelData.name
            x: (modelData.x+2)*board.cellWidth+14
            y: (modelData.y+1)*board.cellHeight+6
            width: board.cellWidth-28; height: board.cellHeight-18
            z: dragArea.drag.active ? 10 : 1
            radius: Style.space(6)
            gradient: Gradient {
              GradientStop { position: 0; color: Qt.tint(Color.background, Qt.alpha(Color.accent, root.selected===machineCard.modelData.id ? 0.25 : 0.12)) }
              GradientStop { position: 1; color: Color.background }
            }
            border.color: root.selected===modelData.id ? Color.accent : Qt.alpha(Color.accent,0.45)
            border.width: root.selected===modelData.id ? 2 : 1
            Rectangle {
              anchors.fill: parent; anchors.margins: -4; z: -1
              radius: Style.space(8); color: "transparent"
              border.width: 3; border.color: Qt.alpha(Color.accent, root.selected===machineCard.modelData.id ? 0.16 : 0.04)
            }
            Rectangle { anchors.top: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; width: Style.space(3); height: Style.space(5); color: Qt.alpha(Color.accent,0.7) }
            Rectangle { anchors.top: parent.bottom; anchors.topMargin: Style.space(5); anchors.horizontalCenter: parent.horizontalCenter; width: Style.space(30); height: Style.space(2); radius: 1; color: Qt.alpha(Color.accent,0.65) }
            Rectangle { x: Style.space(7); y: Style.space(7); width: Style.space(4); height: width; radius: width/2; color: root.state.running ? Color.accent : Qt.alpha(Color.foreground,0.35) }
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
              onReleased: root.moveMachine(machineCard.index, Math.round((machineCard.x-14)/board.cellWidth)-2, Math.round((machineCard.y-6)/board.cellHeight)-1)
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
        Label { text: "◉  PHYSICAL INPUT PRIORITY    ·    "+root.draft.length+" / 9 MACHINES"; font.pixelSize: Style.font.caption; color: Qt.alpha(Color.foreground,0.6) }
        Item { Layout.fillWidth: true }
        Action { text: "Reset draft"; enabled: root.dirty && !root.busy; onClicked: root.reloadDraft() }
        Action { text: apply.running ? "Applying…" : "Apply layout"; enabled: root.dirty && !root.busy; onClicked: root.saveLayout() }
        Action { text: "Close"; enabled: !apply.running; onClicked: root.close() }
      }
    }
  }
}
