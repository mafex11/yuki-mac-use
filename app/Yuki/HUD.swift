import AppKit
import SwiftUI

/// Borderless panels refuse key status by default; the ask-reply text field
/// needs it. nonactivatingPanel keeps the app behind it active either way.
final class KeyableHUDPanel: NSPanel {
    override var canBecomeKey: Bool { true }
}

/// The activity pill: a small floating overlay that shows what the agent is
/// doing while it drives the Mac, with a Stop button. The command bar closes
/// when a task starts; this pill is the task's face until it finishes.
@MainActor
final class HUD: ObservableObject {
    static let shared = HUD()
    private var panel: NSPanel?

    @Published var task = ""            // what the user asked, shown as title
    @Published var line = ""            // current step, human phrasing
    @Published var step = 0
    @Published var maxSteps = 0
    @Published var state: State = .idle
    @Published var resultPreview = ""   // first lines of the final answer
    @Published var queuedPreview: String? = nil
    @Published var question = ""        // pending ask_user question
    @Published var questionOptions: [String] = []
    @Published var answerDraft = ""
    enum State: Equatable { case idle, running, stopping, success, failure, cancelled, asking, paused }

    func begin(task: String) {
        self.task = task
        state = .running
        line = "Figuring out the steps…"
        step = 0
        maxSteps = 0
        resultPreview = ""
        show()
    }

    func setQueued(preview: String) { queuedPreview = preview }
    func clearQueued() { queuedPreview = nil }

    func requestStop() {
        guard state == .running || state == .asking || state == .paused else { return }
        state = .stopping
        line = "Stopping after this step…"
        question = ""
        Task { await Backend.shared.cancelControl() }
    }

    func sendAnswer(_ text: String) {
        guard state == .asking, !text.isEmpty else { return }
        state = .running
        line = "Continuing with your answer…"
        question = ""
        questionOptions = []
        Task { await Backend.shared.answerControl(text) }
    }

    func resumeTask() {
        guard state == .paused else { return }
        state = .running
        line = "Continuing…"
        Task { await Backend.shared.resumeControl() }
    }

    func dismiss() {
        panel?.orderOut(nil)
        state = .idle
    }

    func handle(event o: [String: Any]) {
        guard let type = o["type"] as? String else { return }
        switch type {
        case "state":
            step = (o["step"] as? Int ?? 0) + 1
            maxSteps = o["max_steps"] as? Int ?? 0
        case "tool_call":
            guard state == .running else { break }  // keep "Stopping…" sticky
            let tool = o["tool_name"] as? String ?? ""
            let params = o["tool_params"] as? [String: Any] ?? [:]
            line = Self.friendly(tool: tool, params: params)
        case "done":
            state = .success
            let content = (o["content"] as? String ?? "Done")
            resultPreview = String(content.prefix(160))
            line = "Done"
            fadeAfter(6)
        case "cancelled":
            state = .cancelled
            line = "Stopped"
            resultPreview = ""
            fadeAfter(3)
        case "ask":
            state = .asking
            question = o["question"] as? String ?? "Yuki has a question"
            questionOptions = o["options"] as? [String] ?? []
            answerDraft = ""
            // Key (for typing a reply) without activating our app.
            panel?.makeKeyAndOrderFront(nil)
        case "paused":
            state = .paused
            line = o["reason"] as? String ?? "Paused — you took over."
        case "resumed":
            if state == .paused { state = .running; line = "Continuing…" }
        case "error":
            // While stopping, the agent emits "Stopped by user" as an error
            // before the final cancelled event — don't flash red for that.
            guard state != .stopping else { break }
            state = .failure
            line = String((o["error"] as? String ?? o["content"] as? String ?? "Failed").prefix(160))
            // sticky — dismiss via the ✕ button
        default:
            break
        }
    }

    /// Human phrasing for a tool call — what a person would say they're doing.
    static func friendly(tool: String, params: [String: Any]) -> String {
        func str(_ key: String) -> String { (params[key] as? String) ?? "" }
        switch tool {
        case "app_tool":
            let name = str("name")
            return name.isEmpty ? "Switching apps" : "Opening \(name)"
        case "type_tool":
            let text = str("text")
            return text.isEmpty ? "Typing" : "Typing “\(text.prefix(30))”"
        case "click_tool":
            return "Clicking"
        case "scroll_tool":
            return "Scrolling"
        case "shortcut_tool":
            let keys = str("shortcut")
            return keys.isEmpty ? "Pressing keys"
                : "Pressing \(keys.replacingOccurrences(of: "cmd", with: "⌘"))"
        case "shell_tool":
            return str("mode") == "osascript" ? "Talking to an app" : "Running a command"
        case "wait_tool":
            return "Waiting for the screen"
        case "scrape_tool":
            return "Reading a page"
        case "memory_tool":
            return "Taking notes"
        case "list_app_notes", "read_app_note":
            return "Recalling how this app works"
        case "ask_user_tool":
            return "Waiting for your answer"
        case "spotify_tool", "music_tool":
            let action = str("action")
            let app = tool == "spotify_tool" ? "Spotify" : "Music"
            switch action {
            case "play": return "Pressing play in \(app)"
            case "pause": return "Pausing \(app)"
            case "search": return "Searching \(app)"
            case "play_uri": return "Starting playback in \(app)"
            case "now_playing": return "Checking what's playing"
            default: return "Controlling \(app)"
            }
        case "browser_tool":
            return str("action") == "open_url" ? "Opening a page" : "Checking the browser"
        case "mail_tool": return "Working in Mail"
        case "messages_tool": return "Working in Messages"
        case "notes_tool": return "Working in Notes"
        case "calendar_tool": return "Checking the calendar"
        case "reminders_tool": return "Updating reminders"
        case "clipboard_tool": return "Using the clipboard"
        case "screenshot_tool": return "Taking a screenshot"
        case "web_search_tool": return "Searching the web"
        case "system_tool": return "Adjusting system settings"
        case "contacts_tool": return "Looking up a contact"
        case "shortcuts_tool": return "Running a Shortcut"
        default:
            return tool.replacingOccurrences(of: "_tool", with: "")
                .replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func show() {
        if panel == nil { build() }
        position()
        panel?.orderFront(nil)
    }

    private func fadeAfter(_ secs: Double) {
        let settled = state
        Task {
            try? await Task.sleep(nanoseconds: UInt64(secs * 1_000_000_000))
            if state == settled {
                panel?.orderOut(nil)
                state = .idle
            }
        }
    }

    private func build() {
        let p = KeyableHUDPanel(
            contentRect: NSRect(x: 0, y: 0, width: 340, height: 96),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered, defer: false)
        p.level = .floating
        p.isOpaque = false
        p.backgroundColor = .clear
        p.hasShadow = true
        // The pill accepts clicks (Stop / dismiss) but never becomes key, so
        // it can't steal focus from the app the agent is driving. It sits in
        // a screen corner where agent clicks are very unlikely to land.
        p.ignoresMouseEvents = false
        p.hidesOnDeactivate = false
        p.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
        p.contentView = NSHostingView(rootView: HUDView(hud: self))
        panel = p
    }

    private func position() {
        guard let p = panel, let s = NSScreen.main else { return }
        let f = s.visibleFrame
        let corner = UserDefaults.standard.string(forKey: "yuki.hudCorner") ?? "top-right"
        let m: CGFloat = 16
        let w: CGFloat = 340
        let h: CGFloat = 96
        let x: CGFloat
        let y: CGFloat
        switch corner {
        case "top-left": x = f.minX + m; y = f.maxY - h - m
        case "bottom-right": x = f.maxX - w - m; y = f.minY + m
        case "bottom-left": x = f.minX + m; y = f.minY + m
        default: x = f.maxX - w - m; y = f.maxY - h - m  // top-right
        }
        p.setFrameOrigin(NSPoint(x: x, y: y))
    }
}

struct HUDView: View {
    @ObservedObject var hud: HUD

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                icon
                Text(title)
                    .font(.callout.weight(.medium))
                    .lineLimit(1)
                Spacer(minLength: 4)
                trailingButton
            }
            if !subtitle.isEmpty {
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            if hud.state == .running || hud.state == .stopping, hud.maxSteps > 0 {
                ProgressView(value: Double(min(hud.step, hud.maxSteps)),
                             total: Double(hud.maxSteps))
                    .progressViewStyle(.linear)
                    .controlSize(.small)
                    .tint(hud.state == .stopping ? .orange : .accentColor)
            }
            if hud.state == .asking {
                askUI
            }
            if hud.state == .paused {
                HStack(spacing: 8) {
                    Button("Resume") { hud.resumeTask() }
                        .buttonStyle(.borderedProminent).controlSize(.small)
                    Button("Stop") { hud.requestStop() }
                        .buttonStyle(.bordered).controlSize(.small).tint(.red)
                }
            }
            if let next = hud.queuedPreview {
                Text("next: \(next)").font(.caption2).foregroundStyle(.tertiary)
                    .lineLimit(1)
            }
        }
        .padding(12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
        .frame(width: 340)
    }

    @ViewBuilder private var askUI: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(hud.question)
                .font(.caption)
                .lineLimit(4)
            if !hud.questionOptions.isEmpty {
                // Choice question: one tap per option.
                HStack(spacing: 6) {
                    ForEach(hud.questionOptions, id: \.self) { opt in
                        Button(opt) { hud.sendAnswer(opt) }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                    }
                }
            } else {
                HStack(spacing: 6) {
                    TextField("Type a reply…", text: $hud.answerDraft)
                        .textFieldStyle(.roundedBorder)
                        .controlSize(.small)
                        .onSubmit { hud.sendAnswer(hud.answerDraft) }
                    Button("Send") { hud.sendAnswer(hud.answerDraft) }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                }
            }
        }
    }

    private var title: String {
        switch hud.state {
        case .success: return "Done"
        case .failure: return "Couldn't finish"
        case .cancelled: return "Stopped"
        case .stopping: return "Stopping…"
        case .asking: return "Quick question"
        case .paused: return "Paused — you took over"
        default: return hud.task.isEmpty ? "Working…" : hud.task
        }
    }

    private var subtitle: String {
        switch hud.state {
        case .success: return hud.resultPreview
        case .failure: return hud.line
        case .running, .stopping:
            let steps = hud.maxSteps > 0 ? "  ·  step \(hud.step)/\(hud.maxSteps)" : ""
            return hud.line + steps
        case .paused: return hud.task
        default: return ""
        }
    }

    @ViewBuilder private var icon: some View {
        switch hud.state {
        case .running, .stopping: ProgressView().controlSize(.small)
        case .success: Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
        case .failure: Image(systemName: "xmark.circle.fill").foregroundStyle(.red)
        case .cancelled: Image(systemName: "stop.circle.fill").foregroundStyle(.orange)
        case .asking: Image(systemName: "questionmark.circle.fill").foregroundStyle(.blue)
        case .paused: Image(systemName: "pause.circle.fill").foregroundStyle(.orange)
        case .idle: EmptyView()
        }
    }

    @ViewBuilder private var trailingButton: some View {
        switch hud.state {
        case .running, .asking, .paused:
            Button {
                hud.requestStop()
            } label: {
                Label("Stop", systemImage: "stop.fill")
                    .font(.caption.weight(.semibold))
                    .labelStyle(.titleAndIcon)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .tint(.red)
        case .failure, .success, .cancelled:
            Button {
                hud.dismiss()
            } label: {
                Image(systemName: "xmark")
                    .font(.caption2.weight(.bold))
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
        default:
            EmptyView()
        }
    }
}
