import AppKit

@MainActor
final class MenuBar {
    private var statusItem: NSStatusItem?
    private var pollTimer: Timer?

    func attach() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "Y"
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

        let t = Timer(timeInterval: 0.5, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.statusItem?.button?.title =
                    HUD.shared.state == .running ? "◌" : "Y"
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
