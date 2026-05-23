# Plan J — Menu-bar App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the SwiftUI menu-bar app — the user-visible "Yuki" — that owns the lifecycle of the Python backend, registers the global hotkey, hosts the wakeword listener, exposes the menu-bar popover, and opens the chat overlay or full frontend in the default browser.

**Architecture:** A single SwiftUI `@main` app with `LSUIElement=true` so it runs as an agent (no Dock icon). At launch it: (1) generates a launch token, (2) spawns the bundled Python backend (`Resources/python/bin/python -m yuki.backend.cli`) with the token in the env, (3) waits for `/healthz`, (4) registers a global `Carbon` hotkey for `⌘⇧Y`, (5) shows the menu-bar `NSStatusItem` icon. Quitting the app gracefully stops the backend. A `LaunchAgent` plist installed at first run handles boot-time start.

**Tech Stack:** Swift 5.10, SwiftUI, AppKit (NSStatusItem, NSWorkspace), Carbon (RegisterEventHotKey), Foundation (Process, URL), no external Swift packages required.

**Spec reference:** §3.1 (process model), §9.1–9.4 (invocation surfaces), §10.4 (first-run flow steps 1–6, 13).

**Prerequisite:** Plan I (backend on FastAPI + auth + routers in place). The menu-bar app does not consume any Python directly; it talks to the backend over HTTP only. Task 1 below adds the two menubar-specific backend pieces (`/healthz` readiness probe + `python -m yuki.backend.cli` entry point) — these live in `yuki/backend/` but were intentionally deferred from Plan I because their consumer is the Swift app spawned in Plan J.

---

## File Structure

```
Yuki/
├── app/                                    # NEW — Swift sources
│   ├── Yuki.xcodeproj/                     # generated
│   ├── Yuki/
│   │   ├── YukiApp.swift                   # @main, app delegate
│   │   ├── BackendController.swift         # spawn + supervise + healthcheck
│   │   ├── HotKey.swift                    # Carbon RegisterEventHotKey wrapper
│   │   ├── MenuBar.swift                   # NSStatusItem + popover
│   │   ├── ChatOverlay.swift               # SwiftUI overlay window
│   │   ├── LaunchAgent.swift               # install/uninstall com.yuki.agent.plist
│   │   ├── Token.swift                     # generate/read launch token
│   │   ├── Wakeword.swift                  # opt-in microphone tap (stub)
│   │   └── Info.plist                      # LSUIElement = YES
│   └── Yuki.entitlements
├── yuki/
│   └── backend/
│       ├── cli.py                          # NEW — `python -m yuki.backend.cli`
│       └── routers/
│           └── health.py                   # NEW — GET /healthz (no auth required)
└── tests/
    └── backend/
        └── test_router_health.py           # NEW
```

(Swift code is checked into the repo; `Yuki.xcodeproj` is committed for reproducibility. Briefcase, in Plan K, builds it.)

---

## Task 1 — Backend healthcheck + CLI entry point

**Files:**
- Create: `yuki/backend/cli.py`
- Create: `yuki/backend/routers/health.py`
- Modify: `yuki/backend/server.py`
- Create: `tests/backend/test_router_health.py`

- [ ] **Step 1: Write the failing test**

```python
def test_healthz_no_auth_required(unauth_client):
    r = unauth_client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_health.py -v`
Expected: 404.

- [ ] **Step 3: Implement `yuki/backend/routers/health.py`**

```python
"""Healthz — no-auth liveness probe used by the menu-bar app on startup."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 4: Wire it (no auth dependency)**

In `yuki/backend/server.py` add at the top of `create_app` (before any auth-gated `include_router`):

```python
from yuki.backend.routers import health as health_router
app.include_router(health_router.router)
```

- [ ] **Step 5: Implement `yuki/backend/cli.py`**

```python
"""CLI entry point: `python -m yuki.backend.cli` starts the FastAPI server."""
from __future__ import annotations

import os
import sys

import uvicorn

from yuki.backend.auth import set_active_token
from yuki.backend.server import create_app


def main() -> None:
    token = os.environ.get("YUKI_AUTH_TOKEN")
    if not token:
        print("YUKI_AUTH_TOKEN env var is required", file=sys.stderr)
        sys.exit(2)
    set_active_token(token)
    port = int(os.environ.get("YUKI_PORT", "0"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run + commit**

```bash
cd /Users/mafex/code/personal/Yuki && uv run pytest tests/backend/test_router_health.py -v
git add yuki/backend/routers/health.py yuki/backend/cli.py yuki/backend/server.py tests/backend/test_router_health.py
git commit -m "feat(backend): add /healthz + CLI entry point"
```

---

## Task 2 — Swift project skeleton

`xcodegen` is overkill; we hand-write a minimal Xcode project that Briefcase doesn't even need (Briefcase generates its own). For local dev, we use `swift build` against a `Package.swift` so the Swift code is buildable from CI on macOS.

**Files:**
- Create: `app/Package.swift`
- Create: `app/Yuki/main.swift`
- Create: `app/Yuki/Info.plist`

- [ ] **Step 1: `app/Package.swift`**

```swift
// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "Yuki",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "Yuki", targets: ["Yuki"]),
    ],
    targets: [
        .executableTarget(
            name: "Yuki",
            path: "Yuki",
            resources: [.process("Resources")],
            linkerSettings: [
                .linkedFramework("AppKit"),
                .linkedFramework("Carbon"),
                .linkedFramework("SwiftUI"),
            ]
        ),
    ]
)
```

- [ ] **Step 2: `app/Yuki/main.swift`**

```swift
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
        backend.stop()
        hotkey.unregister()
    }
}
```

- [ ] **Step 3: `app/Yuki/Info.plist`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>com.yuki.app</string>
  <key>CFBundleName</key><string>Yuki</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>LSUIElement</key><true/>
  <key>NSAppleEventsUsageDescription</key>
  <string>Yuki uses AppleScript to control native apps on your behalf.</string>
  <key>NSMicrophoneUsageDescription</key>
  <string>Yuki uses the microphone for optional voice commands.</string>
</dict>
</plist>
```

- [ ] **Step 4: Verify project builds**

```bash
cd /Users/mafex/code/personal/Yuki/app
swift build 2>&1 | tail -20
```

Expected: many "no such file" errors at this point (BackendController, MenuBar, etc. don't exist yet). That's fine — those land in the next tasks.

- [ ] **Step 5: Commit the skeleton**

```bash
cd /Users/mafex/code/personal/Yuki
git add app/Package.swift app/Yuki/main.swift app/Yuki/Info.plist
git commit -m "feat(app): swift package skeleton + LSUIElement Info.plist"
```

---

## Task 3 — `Token.swift`

Generates the launch token (32 bytes hex) using SecRandomCopyBytes and exposes a static API.

**Files:**
- Create: `app/Yuki/Token.swift`

- [ ] **Step 1: Implement**

```swift
import Foundation
import Security

enum TokenError: Error { case randomFailed }

enum Token {
    static func generate() throws -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        let status = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        guard status == errSecSuccess else { throw TokenError.randomFailed }
        return bytes.map { String(format: "%02x", $0) }.joined()
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add app/Yuki/Token.swift
git commit -m "feat(app): add Token generator"
```

---

## Task 4 — `BackendController.swift`

Spawns `Resources/python/bin/python -m yuki.backend.cli` with `YUKI_AUTH_TOKEN` set, polls `/healthz` until success or timeout, returns the chosen port. Stops the process on quit.

**Files:**
- Create: `app/Yuki/BackendController.swift`

- [ ] **Step 1: Implement**

```swift
import Foundation

enum BackendError: Error {
    case missingPython
    case startupTimeout
    case nonZeroExit(Int32, String)
}

actor BackendController {
    private var process: Process?
    private var port: Int = 0

    func startAndWaitForHealth(token: String) async throws -> Int {
        let bundle = Bundle.main.bundleURL
        let pythonURL = bundle
            .appendingPathComponent("Contents/Frameworks/Python.framework/Versions/Current/bin/python3")
        guard FileManager.default.fileExists(atPath: pythonURL.path) else {
            throw BackendError.missingPython
        }

        let chosenPort = try Self.pickPort()
        self.port = chosenPort

        let p = Process()
        p.executableURL = pythonURL
        p.arguments = ["-m", "yuki.backend.cli"]
        var env = ProcessInfo.processInfo.environment
        env["YUKI_AUTH_TOKEN"] = token
        env["YUKI_PORT"] = String(chosenPort)
        p.environment = env
        try p.run()
        self.process = p

        try await Self.waitForHealthz(port: chosenPort, timeoutSeconds: 15)
        return chosenPort
    }

    func stop() {
        process?.terminate()
        process = nil
    }

    private static func pickPort() throws -> Int {
        let socket = socket(AF_INET, SOCK_STREAM, 0)
        defer { close(socket) }
        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")
        addr.sin_port = 0
        var bound = addr
        _ = withUnsafePointer(to: &bound) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(socket, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        var resolved = sockaddr_in()
        _ = withUnsafeMutablePointer(to: &resolved) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                getsockname(socket, $0, &len)
            }
        }
        return Int(UInt16(bigEndian: resolved.sin_port))
    }

    private static func waitForHealthz(port: Int, timeoutSeconds: Double) async throws {
        let deadline = Date().addingTimeInterval(timeoutSeconds)
        let url = URL(string: "http://127.0.0.1:\(port)/healthz")!
        while Date() < deadline {
            if let (_, resp) = try? await URLSession.shared.data(from: url),
               (resp as? HTTPURLResponse)?.statusCode == 200 {
                return
            }
            try? await Task.sleep(nanoseconds: 250_000_000)
        }
        throw BackendError.startupTimeout
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add app/Yuki/BackendController.swift
git commit -m "feat(app): add BackendController for spawn + healthcheck"
```

---

## Task 5 — `HotKey.swift` (Carbon)

Registers `⌘⇧Y` globally. Calls a Swift closure on press. Long-press (>500ms hold) is detected by tracking key-down timestamp and triggering a different callback if held.

**Files:**
- Create: `app/Yuki/HotKey.swift`

- [ ] **Step 1: Implement**

```swift
import AppKit
import Carbon

final class HotKey {
    private var hotKeyRef: EventHotKeyRef?
    private var onTap: (() -> Void)?
    private var onLongPress: (() -> Void)?
    private var keyDownAt: Date?

    func register(
        onTap: @escaping () -> Void,
        onLongPress: (() -> Void)? = nil,
    ) {
        self.onTap = onTap
        self.onLongPress = onLongPress

        let signature: OSType = OSType("YUKI".fourCharCode)
        var hotKeyID = EventHotKeyID(signature: signature, id: 1)
        let modifiers: UInt32 = UInt32(cmdKey | shiftKey)
        let keycode: UInt32 = 16  // 'Y'
        RegisterEventHotKey(keycode, modifiers, hotKeyID,
                            GetApplicationEventTarget(), 0, &hotKeyRef)

        let handler: EventHandlerUPP = { _, eventRef, userData in
            let me = Unmanaged<HotKey>.fromOpaque(userData!).takeUnretainedValue()
            let kind = GetEventKind(eventRef)
            if kind == UInt32(kEventHotKeyPressed) {
                me.keyDownAt = Date()
            } else if kind == UInt32(kEventHotKeyReleased) {
                if let down = me.keyDownAt {
                    let dt = Date().timeIntervalSince(down)
                    if dt > 0.5 { me.onLongPress?() } else { me.onTap?() }
                }
                me.keyDownAt = nil
            }
            return noErr
        }
        var spec = [
            EventTypeSpec(eventClass: OSType(kEventClassKeyboard),
                          eventKind: UInt32(kEventHotKeyPressed)),
            EventTypeSpec(eventClass: OSType(kEventClassKeyboard),
                          eventKind: UInt32(kEventHotKeyReleased)),
        ]
        InstallEventHandler(GetApplicationEventTarget(), handler,
                            spec.count, &spec,
                            Unmanaged.passUnretained(self).toOpaque(), nil)
    }

    func unregister() {
        if let ref = hotKeyRef { UnregisterEventHotKey(ref) }
        hotKeyRef = nil
    }
}

private extension String {
    var fourCharCode: UInt32 {
        var code: UInt32 = 0
        for ch in self.utf8.prefix(4) {
            code = (code << 8) + UInt32(ch)
        }
        return code
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add app/Yuki/HotKey.swift
git commit -m "feat(app): add Carbon hotkey wrapper with long-press detection"
```

---

## Task 5b — `BurstBridge.swift`

Long-press of `⌘⇧Y` calls into the Python backend's `/safety/burst` endpoint (Plan I Task 6b) to engage burst mode for 30 seconds.

**Files:**
- Create: `app/Yuki/BurstBridge.swift`

- [ ] **Step 1: Implement**

```swift
import Foundation

enum BurstBridge {
    static func engage(token: String, port: Int, duration: Double = 30.0) {
        guard let url = URL(string: "http://127.0.0.1:\(port)/safety/burst") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(
            withJSONObject: ["duration": duration],
        )
        URLSession.shared.dataTask(with: req) { _, _, error in
            if let error = error {
                NSLog("BurstBridge engage failed: \(error)")
            }
        }.resume()
    }
}
```

- [ ] **Step 2: Build + commit**

```bash
cd /Users/mafex/code/personal/Yuki/app && swift build 2>&1 | tail -5
cd /Users/mafex/code/personal/Yuki
git add app/Yuki/BurstBridge.swift
git commit -m "feat(app): add BurstBridge HTTP client for long-press hotkey"
```

---

## Task 6 — `MenuBar.swift` + `ChatOverlay.swift` + `LaunchAgent.swift` + `Wakeword.swift`

Bundle the remaining files. They're all small.

**Files:**
- Create: `app/Yuki/MenuBar.swift`
- Create: `app/Yuki/ChatOverlay.swift`
- Create: `app/Yuki/LaunchAgent.swift`
- Create: `app/Yuki/Wakeword.swift`

- [ ] **Step 1: `app/Yuki/MenuBar.swift`**

```swift
import AppKit

final class MenuBar {
    private var statusItem: NSStatusItem?

    func attach(token: String, port: Int) {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "Y"
        let menu = NSMenu()
        menu.addItem(withTitle: "Open chat",
                     action: #selector(openChat),
                     keyEquivalent: "")
            .target = self
        menu.addItem(withTitle: "Open full UI",
                     action: #selector(openUI),
                     keyEquivalent: "")
            .target = self
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Quit Yuki",
                     action: #selector(NSApplication.terminate(_:)),
                     keyEquivalent: "q")
        item.menu = menu
        statusItem = item
        UserDefaults.standard.set(token, forKey: "yuki.token")
        UserDefaults.standard.set(port, forKey: "yuki.port")
    }

    @objc private func openChat() {
        ChatOverlay.toggle(
            token: UserDefaults.standard.string(forKey: "yuki.token") ?? "",
            port: UserDefaults.standard.integer(forKey: "yuki.port"),
        )
    }

    @objc private func openUI() {
        let token = UserDefaults.standard.string(forKey: "yuki.token") ?? ""
        let port = UserDefaults.standard.integer(forKey: "yuki.port")
        let url = URL(string: "http://127.0.0.1:\(port)/?token=\(token)")!
        NSWorkspace.shared.open(url)
    }
}
```

- [ ] **Step 2: `app/Yuki/ChatOverlay.swift`**

```swift
import AppKit
import SwiftUI

@MainActor
enum ChatOverlay {
    private static var window: NSWindow?

    static func toggle(token: String, port: Int) {
        if let w = window, w.isVisible {
            w.orderOut(nil)
            return
        }
        if window == nil {
            let w = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 480, height: 360),
                styleMask: [.titled, .closable, .resizable],
                backing: .buffered, defer: false,
            )
            w.title = "Yuki"
            w.center()
            w.contentView = NSHostingView(rootView: ChatView(token: token, port: port))
            window = w
        }
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}

struct ChatView: View {
    let token: String
    let port: Int
    @State private var input = ""
    @State private var output = ""

    var body: some View {
        VStack {
            ScrollView { Text(output).frame(maxWidth: .infinity, alignment: .leading) }
            HStack {
                TextField("Ask Yuki", text: $input).onSubmit { send() }
                Button("Send") { send() }
            }
        }
        .padding()
    }

    private func send() {
        let url = URL(string: "http://127.0.0.1:\(port)/chat")!
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body = try? JSONSerialization.data(withJSONObject: ["message": input])
        req.httpBody = body
        let task = URLSession.shared.dataTask(with: req) { data, _, _ in
            DispatchQueue.main.async {
                output += "\n" + (data.flatMap { String(data: $0, encoding: .utf8) } ?? "")
            }
        }
        task.resume()
        input = ""
    }
}
```

- [ ] **Step 3: `app/Yuki/LaunchAgent.swift`**

```swift
import Foundation

enum LaunchAgent {
    static let label = "com.yuki.agent"

    static func install() throws {
        let bundle = Bundle.main.bundleURL.path
        let plist: [String: Any] = [
            "Label": label,
            "ProgramArguments": ["\(bundle)/Contents/MacOS/Yuki"],
            "RunAtLoad": true,
            "KeepAlive": true,
        ]
        let dir = FileManager.default
            .urls(for: .libraryDirectory, in: .userDomainMask)
            .first!
            .appendingPathComponent("LaunchAgents")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("\(label).plist")
        let data = try PropertyListSerialization.data(
            fromPropertyList: plist, format: .xml, options: 0,
        )
        try data.write(to: url)
    }

    static func uninstall() throws {
        let url = FileManager.default
            .urls(for: .libraryDirectory, in: .userDomainMask)
            .first!
            .appendingPathComponent("LaunchAgents/\(label).plist")
        try? FileManager.default.removeItem(at: url)
    }
}
```

- [ ] **Step 4: `app/Yuki/Wakeword.swift` (stub)**

```swift
import Foundation

enum Wakeword {
    static func startIfEnabled() {
        // Real impl: streaming Whisper + small wakeword model.
        // Off by default per spec §9.2; v1.x follow-up implements this.
    }
}
```

- [ ] **Step 5: Build and verify**

```bash
cd /Users/mafex/code/personal/Yuki/app && swift build 2>&1 | tail -10
```

Expected: clean build (or only warnings — no errors).

- [ ] **Step 6: Commit**

```bash
cd /Users/mafex/code/personal/Yuki
git add app/Yuki/MenuBar.swift app/Yuki/ChatOverlay.swift app/Yuki/LaunchAgent.swift app/Yuki/Wakeword.swift
git commit -m "feat(app): add MenuBar + ChatOverlay + LaunchAgent + Wakeword stub"
```

---

## Wrap-up

After Task 6:
- `swift build` produces a working `Yuki` executable that, given a sibling Python framework + `yuki.backend.cli`, will:
  - Generate a token, spawn the backend, wait for `/healthz`
  - Show menu-bar icon with chat / full-UI / quit
  - Respond to `⌘⇧Y` with overlay toggle
  - Long-press of `⌘⇧Y` triggers burst-mode via `BurstBridge` → backend `/safety/burst`
  - Quitting cleans up the backend

The Python framework + `yuki.backend.cli` are bundled by Briefcase in Plan K.

Acceptance:
- `swift build` succeeds in `app/`
- `uv run pytest tests/backend/test_router_health.py -v` passes
- Manually: dropping a built `python3` and `yuki/` next to the binary lets the menubar app launch and respond to `⌘⇧Y`

