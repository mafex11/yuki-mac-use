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

    func chat(_ msg: String) async -> (reply: String, badge: String, capture: String?) {
        var reply = ""
        var badge = ""
        var capture: String? = nil
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
                    capture = o["capture_suggestion"] as? String
                } else if type == "error" {
                    reply = "[error] " + (o["content"] as? String ?? "")
                }
            }, onDone: { cont.resume() })
        }
        return (reply, badge, capture)
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
            // NOTE(v0.1): single-slot queued preview — with 3+ tasks queued at
            // once, starting one clears the "next:" line even though more remain.
            // Acceptable for v0.1 (users rarely queue >1); a real fix needs a
            // queue-depth counter or an ordered pending list.
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

    /// The provider the backend is actually configured to use (from
    /// app_state.json), so the UI reflects reality instead of a local default.
    func currentProvider() async -> String {
        guard let data = try? await client.getJSON(path: "/settings/provider"),
              let o = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else { return "google" }
        return (o["provider"] as? String) ?? "google"
    }

    /// The model the backend is configured to use (from app_state.json), so
    /// the Ollama picker can highlight the active model.
    func currentModel() async -> String {
        guard let data = try? await client.getJSON(path: "/settings/provider"),
              let o = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else { return "" }
        return (o["model"] as? String) ?? ""
    }

    /// Read the saved api key straight from the Keychain (the app is the
    /// trusted binary). Used to prepopulate the Settings field so the user
    /// sees their key is stored.
    func savedKey(for provider: String) -> String {
        guard provider == "google" || provider == "anthropic" else { return "" }
        return Keychain.get(account: provider) ?? ""
    }

    struct OllamaModel: Identifiable {
        var id: String { name }
        let name: String
        let tools: Bool   // can do control tasks
    }
    struct RecommendedModel: Identifiable {
        var id: String { name }
        let name: String
        let size: String
        let note: String
    }

    /// Installed local Ollama models + tool-capability + recommendations.
    /// `running` is false when Ollama isn't reachable (UI falls back to manual).
    func ollamaModels() async -> (running: Bool,
                                  models: [OllamaModel],
                                  recommended: [RecommendedModel]) {
        guard let data = try? await client.getJSON(
                path: "/settings/provider/ollama/models"),
              let o = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else { return (false, [], []) }
        let running = o["running"] as? Bool ?? false
        let models: [OllamaModel] = (o["models"] as? [[String: Any]] ?? [])
            .compactMap { d in
                guard let name = d["name"] as? String else { return nil }
                return OllamaModel(name: name, tools: d["tools"] as? Bool ?? false)
            }
        let recommended: [RecommendedModel] = (o["recommended"] as? [[String: Any]] ?? [])
            .compactMap { d in
                guard let name = d["name"] as? String else { return nil }
                return RecommendedModel(name: name,
                                        size: d["size"] as? String ?? "",
                                        note: d["note"] as? String ?? "")
            }
        return (running, models, recommended)
    }

    /// Pull an Ollama model, streaming progress. onProgress gets (percent,
    /// status); resolves true on success, false on error.
    func pullModel(_ model: String,
                   onProgress: @escaping (Int, String) -> Void) async -> Bool {
        var ok = false
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            guard let body = try? JSONSerialization.data(
                    withJSONObject: ["model": model]) else { cont.resume(); return }
            client.streamSSE(path: "/settings/provider/ollama/pull", body: body,
                             onEvent: { line in
                guard let d = line.data(using: .utf8),
                      let o = try? JSONSerialization.jsonObject(with: d)
                        as? [String: Any] else { return }
                switch o["type"] as? String {
                case "progress":
                    let pct = o["percent"] as? Int ?? 0
                    let status = o["status"] as? String ?? ""
                    Task { @MainActor in onProgress(pct, status) }
                case "done": ok = true
                default: break
                }
            }, onDone: { cont.resume() })
        }
        return ok
    }

    func saveProvider(_ provider: String, model: String? = nil) async {
        var payload: [String: Any] = ["provider": provider]
        if let model = model { payload["model"] = model }
        guard let body = try? JSONSerialization.data(withJSONObject: payload)
        else { return }
        _ = try? await client.postJSON(path: "/settings/provider", body: body)
    }

    /// Push a provider's api key to the backend in-process. The app is the only
    /// binary the Keychain ACL trusts, so it reads the key silently (no GUI
    /// prompt) and hands it over; the headless backend never shells out to
    /// `security`, which would block on an unanswerable access prompt.
    func pushKey(for provider: String) async {
        guard provider == "google" || provider == "anthropic",
              let key = Keychain.get(account: provider), !key.isEmpty,
              let body = try? JSONSerialization.data(
                withJSONObject: ["provider": provider, "key": key])
        else { return }
        _ = try? await client.postJSON(path: "/settings/provider/key", body: body)
    }

    func testConnection() async -> Bool {
        guard let data = try? await client.getJSON(
                path: "/settings/provider/test"),
              let o = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else { return false }
        return (o["ok"] as? Bool) ?? false
    }

    // MARK: - memory facts

    struct Fact: Identifiable {
        let id: String
        let section: String
        let title: String
        let text: String
    }

    func facts() async -> [Fact] {
        guard let data = try? await client.getJSON(path: "/facts"),
              let o = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let arr = o["facts"] as? [[String: Any]] else { return [] }
        return arr.compactMap { d in
            guard let id = d["id"] as? String else { return nil }
            return Fact(id: id,
                        section: d["section"] as? String ?? "",
                        title: d["title"] as? String ?? "",
                        text: d["text"] as? String ?? "")
        }
    }

    @discardableResult
    func addFact(_ text: String) async -> Bool {
        guard let body = try? JSONSerialization.data(withJSONObject: ["text": text])
        else { return false }
        return (try? await client.postJSON(path: "/facts", body: body)) != nil
    }

    @discardableResult
    func forgetFact(id: String) async -> Bool {
        return (try? await client.deleteJSON(path: "/facts/\(id)")) != nil
    }

    func memorySettings() async -> (learner: Bool, ask: Bool) {
        guard let data = try? await client.getJSON(path: "/facts/settings"),
              let o = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return (true, true) }
        return (o["learner_enabled"] as? Bool ?? true,
                o["ask_before_remember"] as? Bool ?? true)
    }

    func setMemorySettings(learner: Bool? = nil, ask: Bool? = nil) async {
        var payload: [String: Any] = [:]
        if let learner = learner { payload["learner_enabled"] = learner }
        if let ask = ask { payload["ask_before_remember"] = ask }
        guard let body = try? JSONSerialization.data(withJSONObject: payload) else { return }
        _ = try? await client.postJSON(path: "/facts/settings", body: body)
    }

    // MARK: - control streamed into the command bar

    /// Run a control task, forwarding every SSE event to `onEvent` (for the
    /// bar's inline activity) while the HUD also reflects status. Resolves
    /// when the task completes.
    func runControlInBar(_ msg: String,
                         onEvent: @escaping ([String: Any]) -> Void) async {
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            guard let body = try? JSONSerialization.data(
                    withJSONObject: ["message": msg]) else { cont.resume(); return }
            client.streamSSE(path: "/chat/control", body: body, onEvent: { line in
                guard let d = line.data(using: .utf8),
                      let o = try? JSONSerialization.jsonObject(with: d)
                        as? [String: Any] else { return }
                Task { @MainActor in
                    HUD.shared.handle(event: o)
                    onEvent(o)
                }
            }, onDone: { cont.resume() })
        }
    }

    /// Ask the backend to stop the running control task at its next step.
    func cancelControl() async {
        _ = try? await client.postJSON(
            path: "/chat/control/cancel", body: Data("{}".utf8))
    }

    /// Deliver the user's reply to a pending mid-task question.
    func answerControl(_ answer: String) async {
        guard let body = try? JSONSerialization.data(
                withJSONObject: ["answer": answer]) else { return }
        _ = try? await client.postJSON(path: "/chat/control/answer", body: body)
    }

    /// Resume a task paused because the user took over the mouse/keyboard.
    func resumeControl() async {
        _ = try? await client.postJSON(
            path: "/chat/control/resume", body: Data("{}".utf8))
    }
}
