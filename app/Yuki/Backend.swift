import Foundation

@MainActor
final class Backend {
    static let shared = Backend()

    private let client = UDSClient(socketPath: NSHomeDirectory() +
        "/Library/Application Support/Yuki/yuki.sock")

    // MARK: - routing

    func route(_ msg: String) async -> String {
        guard let body = try? JSONSerialization.data(
                withJSONObject: ["message": msg]),
              let data = try? await client.postJSON(path: "/route", body: body),
              let obj = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else { return "chat" }
        return (obj["route"] as? String) ?? "chat"
    }

    // MARK: - chat (collects the single final 'done')

    func chat(_ msg: String) async -> (reply: String, badge: String) {
        var reply = ""
        var badge = ""
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            guard let body = try? JSONSerialization.data(
                    withJSONObject: ["message": msg]) else {
                cont.resume(); return
            }
            client.streamSSE(path: "/chat", body: body, onEvent: { line in
                guard let d = line.data(using: .utf8),
                      let o = try? JSONSerialization.jsonObject(with: d)
                        as? [String: Any] else { return }
                let type = o["type"] as? String
                if type == "done" {
                    reply = o["content"] as? String ?? ""
                    badge = o["ctx_badge"] as? String ?? ""
                } else if type == "error" {
                    reply = "[error] " + (o["content"] as? String ?? "")
                }
            }, onDone: { cont.resume() })
        }
        return (reply, badge)
    }

    // MARK: - control (forwards every event to the HUD)

    private var controlTail: Task<Void, Never>?

    /// FIFO-serialize control runs so two desktop tasks never fight the mouse.
    /// Queued tasks surface as "next:" in the HUD.
    func enqueueControl(_ msg: String) {
        let previous = controlTail
        if previous != nil {
            HUD.shared.setQueued(preview: msg)
        }
        controlTail = Task { @MainActor [weak self] in
            await previous?.value
            guard let self else { return }
            HUD.shared.clearQueued()
            HUD.shared.begin(task: msg)
            await self.runControl(msg)
        }
    }

    func runControl(_ msg: String) async {
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            guard let body = try? JSONSerialization.data(
                    withJSONObject: ["message": msg]) else {
                cont.resume(); return
            }
            client.streamSSE(path: "/chat/control", body: body, onEvent: { line in
                guard let d = line.data(using: .utf8),
                      let o = try? JSONSerialization.jsonObject(with: d)
                        as? [String: Any] else { return }
                Task { @MainActor in HUD.shared.handle(event: o) }
            }, onDone: { cont.resume() })
        }
    }

    // MARK: - status / history controls

    func status() async -> (badge: String, percent: Int) {
        guard let data = try? await client.getJSON(path: "/chat/status"),
              let o = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else { return ("", 0) }
        return (o["ctx_badge"] as? String ?? "", o["ctx_percent"] as? Int ?? 0)
    }

    func clear() async -> String {
        guard let data = try? await client.postJSON(
                path: "/chat/clear", body: Data("{}".utf8)),
              let o = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else { return "" }
        return o["ctx_badge"] as? String ?? ""
    }

    func compact() async -> String {
        guard let data = try? await client.postJSON(
                path: "/chat/compact", body: Data("{}".utf8)),
              let o = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else { return "" }
        return o["ctx_badge"] as? String ?? ""
    }

    // MARK: - provider config (first-run / settings)

    func saveProvider(_ provider: String, model: String? = nil) async {
        var payload: [String: Any] = ["provider": provider]
        if let model = model { payload["model"] = model }
        guard let body = try? JSONSerialization.data(withJSONObject: payload)
        else { return }
        _ = try? await client.postJSON(path: "/settings/provider", body: body)
    }

    func testConnection() async -> Bool {
        guard let data = try? await client.getJSON(
                path: "/settings/provider/test"),
              let o = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else { return false }
        return (o["ok"] as? Bool) ?? false
    }
}
