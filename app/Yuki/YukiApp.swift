import AppKit
import SwiftUI

@main
struct YukiApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    var body: some Scene {
        Settings { EmptyView() }
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private let backend = BackendController()
    private let menu = MenuBar()
    private let hotkey = HotKey()

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Menu-bar app (no Dock icon) that can STILL activate + own a key
        // window. Set in code because `swift run` (and bare executables) don't
        // apply Info.plist's LSUIElement, which would otherwise leave the app
        // at .prohibited — unable to become active, so keystrokes leak to the
        // previously-frontmost app.
        NSApp.setActivationPolicy(.accessory)

        menu.attach()
        hotkey.register(
            onTap: { CommandBar.shared.toggle() },
            onLongPress: nil
        )
        Task {
            do {
                try await backend.start()
                FirstRun.runIfNeeded()
            } catch {
                NSLog("Yuki backend failed to start: \(error)")
                let alert = NSAlert()
                alert.messageText = "Yuki couldn't start its engine"
                alert.informativeText =
                    "The backend failed to launch. Check ~/Library/Application Support/Yuki/python.log.\n\n\(error)"
                alert.runModal()
            }
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        Task { await backend.stop() }
        hotkey.unregister()
    }
}
