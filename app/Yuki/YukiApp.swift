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
        Task {
            do {
                let token = try Token.generate()
                let port = try await backend.startAndWaitForHealth(token: token)
                menu.attach()
                hotkey.register(
                    onTap: { CommandBar.shared.toggle() },
                    onLongPress: { BurstBridge.engage(token: token, port: port) }
                )
            } catch {
                NSLog("Yuki failed to start: \(error)")
                NSApp.terminate(nil)
            }
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        Task { await backend.stop() }
        hotkey.unregister()
    }
}
