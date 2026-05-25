import AppKit
import SwiftUI

@main
struct YukiApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    var body: some Scene {
        Settings { EmptyView() }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let backend = BackendController()
    private let menu = MenuBar()
    private let hotkey = HotKey()

    func applicationDidFinishLaunching(_ notification: Notification) {
        Task {
            do {
                let token = try Token.generate()
                let port = try await backend.startAndWaitForHealth(token: token)
                menu.attach(token: token, port: port)
                hotkey.register(
                    onTap: { ChatOverlay.toggle(token: token, port: port) },
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
