import AppKit

@MainActor
final class MenuBar {
    private var statusItem: NSStatusItem?
    private var pollTimer: Timer?

    func attach() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.image = StatusIcon.image()
        let menu = NSMenu()

        let bar = NSMenuItem(title: "Open command bar",
                             action: #selector(openBar), keyEquivalent: "")
        bar.target = self
        menu.addItem(bar)

        let settings = NSMenuItem(title: "Settings…",
                                  action: #selector(openSettings), keyEquivalent: ",")
        settings.target = self
        menu.addItem(settings)

        let logs = NSMenuItem(title: "Reveal logs in Finder",
                              action: #selector(revealLogs), keyEquivalent: "")
        logs.target = self
        menu.addItem(logs)

        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit Yuki",
                                action: #selector(NSApplication.terminate(_:)),
                                keyEquivalent: "q"))
        item.menu = menu
        statusItem = item

        // Animate the snowflake spokes while a task runs (8fps shimmer);
        // static mark otherwise. Skip redraws when nothing changed.
        var phase = 0.0
        var wasRunning = false
        let t = Timer(timeInterval: 0.125, repeats: true) { [weak self] _ in
            Task { @MainActor in
                let running = HUD.shared.state == .running
                    || HUD.shared.state == .stopping
                if running {
                    phase = (phase + 0.06).truncatingRemainder(dividingBy: 1.0)
                    self?.statusItem?.button?.image =
                        StatusIcon.image(running: true, phase: phase)
                } else if wasRunning {
                    self?.statusItem?.button?.image = StatusIcon.image()
                }
                wasRunning = running
            }
        }
        RunLoop.main.add(t, forMode: .common)
        pollTimer = t
    }

    @objc private func openBar() { CommandBar.shared.toggle() }
    @objc private func openSettings() { SettingsWindow.show() }

    @objc private func revealLogs() {
        let dir = NSHomeDirectory() + "/Library/Application Support/Yuki"
        NSWorkspace.shared.selectFile(nil, inFileViewerRootedAtPath: dir)
    }
}
