import AppKit

final class MenuBar {
    private var statusItem: NSStatusItem?

    func attach(token: String, port: Int) {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "Y"
        let menu = NSMenu()
        let chatItem = NSMenuItem(title: "Open chat",
                                   action: #selector(openChat),
                                   keyEquivalent: "")
        chatItem.target = self
        menu.addItem(chatItem)
        let uiItem = NSMenuItem(title: "Open full UI",
                                 action: #selector(openUI),
                                 keyEquivalent: "")
        uiItem.target = self
        menu.addItem(uiItem)
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit Yuki",
                                 action: #selector(NSApplication.terminate(_:)),
                                 keyEquivalent: "q"))
        item.menu = menu
        statusItem = item
        UserDefaults.standard.set(token, forKey: "yuki.token")
        UserDefaults.standard.set(port, forKey: "yuki.port")
    }

    @MainActor @objc private func openChat() {
        CommandBar.shared.toggle()
    }

    @objc private func openUI() {
        let token = UserDefaults.standard.string(forKey: "yuki.token") ?? ""
        let port = UserDefaults.standard.integer(forKey: "yuki.port")
        let url = URL(string: "http://127.0.0.1:\(port)/?token=\(token)")!
        NSWorkspace.shared.open(url)
    }
}
