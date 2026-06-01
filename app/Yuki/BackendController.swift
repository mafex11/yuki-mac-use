import Foundation

enum BackendError: Error { case startupTimeout }

actor BackendController {
    private var process: Process?

    private var socketPath: String {
        NSHomeDirectory() + "/Library/Application Support/Yuki/yuki.sock"
    }

    /// Spawn the Python backend over UDS. Prefers a bundled interpreter inside
    /// the .app; falls back to `uv run` from the repo for dev builds.
    func start() async throws {
        // Clean any stale socket from a prior crashed run.
        try? FileManager.default.removeItem(atPath: socketPath)
        try? FileManager.default.createDirectory(
            atPath: (socketPath as NSString).deletingLastPathComponent,
            withIntermediateDirectories: true)

        let p = Process()
        let res = Bundle.main.resourceURL
        let bundledPython = res?
            .appendingPathComponent("python/bin/python3").path

        let timeout: TimeInterval
        if let bundledPython = bundledPython,
           FileManager.default.fileExists(atPath: bundledPython) {
            // Bundled (production) mode.
            p.executableURL = URL(fileURLWithPath: bundledPython)
            p.arguments = ["-m", "yuki.backend.cli", "--uds"]
            var env = ProcessInfo.processInfo.environment
            env["PYTHONPATH"] = res!
                .appendingPathComponent("python/lib/python3.12/site-packages").path
            env["TIKTOKEN_CACHE_DIR"] = res!
                .appendingPathComponent("tiktoken").path
            p.environment = env
            timeout = 25
        } else {
            // Dev fallback: run from the repo via uv.
            p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            p.arguments = ["uv", "run", "python", "-m", "yuki.backend.cli", "--uds"]
            p.currentDirectoryURL = URL(
                fileURLWithPath: Self.devRepoRoot())
            timeout = 90
        }

        // Pipe Python stdio to a log file.
        let logPath = (socketPath as NSString).deletingLastPathComponent
            + "/python.log"
        FileManager.default.createFile(atPath: logPath, contents: nil)
        if let handle = FileHandle(forWritingAtPath: logPath) {
            p.standardOutput = handle
            p.standardError = handle
        }

        try p.run()
        self.process = p
        do {
            try await waitForSocket(timeout: timeout)
        } catch {
            p.terminate()
            self.process = nil
            throw error
        }
    }

    func stop() {
        process?.terminate()
        process = nil
    }

    private func waitForSocket(timeout: TimeInterval) async throws {
        let client = UDSClient(socketPath: socketPath)
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if FileManager.default.fileExists(atPath: socketPath) {
                if let _ = try? await client.getJSON(path: "/healthz") {
                    return
                }
            }
            try? await Task.sleep(nanoseconds: 300_000_000)
        }
        throw BackendError.startupTimeout
    }

    /// Best-effort repo root for dev mode: walk up from this source file is
    /// not possible at runtime, so use an env override or a hardcoded default.
    private static func devRepoRoot() -> String {
        if let override = ProcessInfo.processInfo.environment["YUKI_REPO_ROOT"] {
            return override
        }
        return NSHomeDirectory() + "/code/personal/Yuki"
    }
}
