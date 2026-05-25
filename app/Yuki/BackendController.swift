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
        let s = socket(AF_INET, SOCK_STREAM, 0)
        defer { close(s) }
        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")
        addr.sin_port = 0
        var bound = addr
        _ = withUnsafePointer(to: &bound) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(s, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        var resolved = sockaddr_in()
        _ = withUnsafeMutablePointer(to: &resolved) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                getsockname(s, $0, &len)
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
