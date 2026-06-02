// app/Yuki/LaunchAgentManager.swift
import Foundation

/// Installs/removes the daily-learner LaunchAgent. The learner distills
/// recorded task episodes into reusable app-notes; it's gated by the
/// "Daily learning" toggle in Settings.
enum LaunchAgentManager {
    static let label = "com.yuki.feedback.learner"

    private static var plistURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/LaunchAgents/\(label).plist")
    }

    /// Bundled interpreter + site-packages, matching BackendController.
    private static func pythonAndEnv() -> (python: String, pythonPath: String)? {
        guard let res = Bundle.main.resourceURL else { return nil }
        let python = res.appendingPathComponent("python/bin/python3").path
        guard FileManager.default.fileExists(atPath: python) else { return nil }
        let site = res
            .appendingPathComponent("python/lib/python3.12/site-packages").path
        return (python, site)
    }

    static func enable() {
        guard let (python, site) = pythonAndEnv() else {
            NSLog("learner: no bundled python; skipping LaunchAgent install")
            return
        }
        let plist: [String: Any] = [
            "Label": label,
            "ProgramArguments": [python, "-m", "yuki.feedback.cli"],
            "EnvironmentVariables": ["PYTHONPATH": site],
            "StartCalendarInterval": ["Hour": 3, "Minute": 0],
            "RunAtLoad": false,
            "StandardErrorPath": FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Application Support/Yuki/learner.log").path,
        ]
        do {
            try FileManager.default.createDirectory(
                at: plistURL.deletingLastPathComponent(),
                withIntermediateDirectories: true)
            let data = try PropertyListSerialization.data(
                fromPropertyList: plist, format: .xml, options: 0)
            try data.write(to: plistURL)
            run(["launchctl", "unload", plistURL.path])  // idempotent
            let loadStatus = run(["launchctl", "load", plistURL.path])
            if loadStatus != 0 {
                NSLog("learner: launchctl load exited \(loadStatus)")
            }
        } catch {
            NSLog("learner: failed to install LaunchAgent: \(error)")
        }
    }

    static func disable() {
        let status = run(["launchctl", "unload", plistURL.path])
        if status != 0 {
            NSLog("learner: launchctl unload exited \(status) (may already be unloaded)")
        }
        try? FileManager.default.removeItem(at: plistURL)
    }

    /// Reconcile install state with the desired toggle at launch.
    static func reconcile(enabled: Bool) {
        if enabled { enable() } else { disable() }
    }

    @discardableResult
    private static func run(_ args: [String]) -> Int32 {
        guard let first = args.first else { return -1 }
        let p = Process()
        // launchctl lives at /bin/launchctl; resolve via /usr/bin/env so we
        // don't hardcode an absolute path but still avoid shell interpretation.
        p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        p.arguments = [first] + Array(args.dropFirst())
        do { try p.run(); p.waitUntilExit(); return p.terminationStatus }
        catch {
            NSLog("learner: command \(args.first ?? "?") failed: \(error)")
            return -1
        }
    }
}
