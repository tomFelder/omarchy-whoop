import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui

BarWidget {
    id: root
    moduleName: "community.whoop"
    property var state: ({})
    property double now: Date.now() / 1000
    readonly property bool live: state.status === "live" && state.bpm > 0
        && now - (state.measured_at || 0) < 15
    readonly property string statusText: {
        if (live) return "Live heart rate"
        if (state.status === "no_contact") return "Check band contact"
        if (state.status === "connecting") return "Connecting to WHOOP…"
        if (state.status === "waiting") return "Waiting for heart rate…"
        return "No live reading — check Heart Rate Broadcast"
    }
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    FileView {
        id: stateFile
        path: Quickshell.env("XDG_RUNTIME_DIR") + "/omarchy-whoop/state.json"
        printErrors: false
        onLoaded: {
            try { root.state = JSON.parse(text()) }
            catch (e) { root.state = ({}) }
        }
        onLoadFailed: root.state = ({})
    }
    Timer {
        interval: 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            root.now = Date.now() / 1000
            stateFile.reload()
        }
    }
    WidgetButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: root.vertical ? "♥\n" + (root.live ? root.state.bpm : "—")
                            : "♥ " + (root.live ? root.state.bpm + " bpm" : "—")
        dimmed: !root.live
        pressable: false
        tooltipText: "WHOOP · " + root.statusText
            + (root.state.battery !== null && root.state.battery !== undefined
               ? "\nBand battery: " + root.state.battery + "%" : "")
    }
}
