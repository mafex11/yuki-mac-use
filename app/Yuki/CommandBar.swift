import AppKit
import SwiftUI

/// A borderless panel that can still become the key window (so its text field
/// can receive keystrokes) and dismisses on Escape.
final class KeyablePanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }

    override func cancelOperation(_ sender: Any?) {
        // Esc closes the command bar (via the shared controller so the
        // click monitor is torn down too).
        CommandBar.shared.close()
    }
}

@MainActor
final class CommandBar {
    static let shared = CommandBar()
    private var panel: NSPanel?
    private var clickMonitor: Any?

    /// True while a control task is streaming into the bar. Suppresses
    /// click-outside dismissal so the agent driving OTHER apps (which the
    /// global monitor would otherwise see as an outside click) can't close
    /// the bar mid-task.
    var isRunningControl = false

    static let focusRequest = Notification.Name("yuki.commandbar.focus")

    func toggle() {
        if let p = panel, p.isVisible {
            removeClickMonitor()
            p.orderOut(nil)
            return
        }
        if panel == nil { build() }
        position()
        // Accessory apps need an explicit activate to own the key window;
        // order the panel front and make it key so its text field gets keys.
        NSApp.activate(ignoringOtherApps: true)
        panel?.makeKeyAndOrderFront(nil)
        panel?.makeFirstResponder(panel?.contentView)
        installClickMonitor()
        // Re-request text-field focus on every open (onAppear only fires once
        // because the panel/host view is reused across toggles).
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
            NSApp.activate(ignoringOtherApps: true)
            self.panel?.makeKey()
            NotificationCenter.default.post(name: Self.focusRequest, object: nil)
        }
    }

    func close() {
        removeClickMonitor()
        panel?.orderOut(nil)
    }

    private func installClickMonitor() {
        guard clickMonitor == nil else { return }
        clickMonitor = NSEvent.addGlobalMonitorForEvents(
            matching: [.leftMouseDown, .rightMouseDown]) { [weak self] _ in
            guard let self, !self.isRunningControl else { return }
            self.close()
        }
    }

    private func removeClickMonitor() {
        if let m = clickMonitor { NSEvent.removeMonitor(m); clickMonitor = nil }
    }

    private func build() {
        let p = KeyablePanel(
            contentRect: NSRect(x: 0, y: 0, width: 720, height: 420),
            styleMask: [.borderless],
            backing: .buffered, defer: false)
        p.level = .floating
        p.isOpaque = false
        p.backgroundColor = .clear
        p.hasShadow = true
        p.isMovableByWindowBackground = true
        p.hidesOnDeactivate = false
        p.contentView = NSHostingView(rootView: CommandBarView())
        panel = p
    }

    private func position() {
        guard let p = panel, let screen = NSScreen.main else { return }
        let f = screen.visibleFrame
        let x = f.midX - p.frame.width / 2
        let y = f.maxY - f.height * 0.20 - p.frame.height
        p.setFrameOrigin(NSPoint(x: x, y: y))
    }
}

struct CommandBarView: View {
    @State private var input = ""
    @State private var history: [Turn] = []
    @State private var liveActivity: String? = nil   // transient "working on it" line
    @State private var ctxBadge = ""
    @State private var modelLabel = ""   // e.g. "ollama · qwen2.5:3b"
    @State private var busy = false
    @FocusState private var inputFocused: Bool
    @State private var pendingCapture: String? = nil
    @State private var askBeforeRemember = true

    struct Turn: Identifiable {
        let id = UUID()
        let role: String   // "human" | "ai" | "error"
        let text: String
    }

    private static let verbMap: [String: String] = [
        "app_tool": "Switching app", "click_tool": "Clicking",
        "type_tool": "Typing", "shortcut_tool": "Pressing keys",
        "shell_tool": "Running", "scroll_tool": "Scrolling",
        "scrape_tool": "Reading screen", "wait_tool": "Waiting",
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Conversation on top, scrolls, newest at bottom.
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(history) { turn in
                            Text(turn.role == "human" ? "❯ \(turn.text)" : turn.text)
                                .font(.callout)
                                .textSelection(.enabled)
                                .foregroundStyle(color(for: turn.role))
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .id(turn.id)
                        }
                        if let activity = liveActivity {
                            HStack(spacing: 8) {
                                ProgressView().controlSize(.small)
                                Text(activity).font(.callout).foregroundStyle(.blue)
                            }
                            .id("live")
                        }
                    }
                    .padding(16)
                }
                .onChange(of: history.count) { _ in scrollToEnd(proxy) }
                .onChange(of: liveActivity) { _ in scrollToEnd(proxy) }
            }

            if let capture = pendingCapture {
                HStack(spacing: 8) {
                    Text("Remember: \(capture)").font(.caption).foregroundStyle(.secondary)
                        .lineLimit(2)
                    Spacer()
                    Button("Yes") {
                        Task { await Backend.shared.addFact(capture); pendingCapture = nil }
                    }.controlSize(.small)
                    Button("No") { pendingCapture = nil }.controlSize(.small)
                }
                .padding(.horizontal, 16).padding(.bottom, 8)
            }

            Divider()

            // Input pinned at the bottom.
            HStack(spacing: 8) {
                Text("❯").foregroundStyle(.blue).font(.title3)
                TextField("Ask Yuki…", text: $input)
                    .textFieldStyle(.plain)
                    .font(.title3)
                    .disabled(busy)
                    .focused($inputFocused)
                    .onSubmit { submit() }
                if !modelLabel.isEmpty {
                    Text(modelLabel)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .help("Active provider · model")
                }
                Text(ctxBadge).font(.caption2).foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(.regularMaterial)
        }
        .frame(width: 720, height: 420)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
        .onAppear {
            loadStatus()
            inputFocused = true
            Task { askBeforeRemember = await Backend.shared.memorySettings().ask }
        }
        .onReceive(NotificationCenter.default.publisher(
            for: CommandBar.focusRequest)) { _ in inputFocused = true }
    }

    private func color(for role: String) -> Color {
        switch role {
        case "human": return .secondary
        case "error": return .red
        default: return .primary
        }
    }

    private func scrollToEnd(_ proxy: ScrollViewProxy) {
        withAnimation {
            if liveActivity != nil { proxy.scrollTo("live", anchor: .bottom) }
            else if let last = history.last { proxy.scrollTo(last.id, anchor: .bottom) }
        }
    }

    private func submit() {
        let msg = input.trimmingCharacters(in: .whitespaces)
        guard !msg.isEmpty, !busy else { return }
        input = ""
        pendingCapture = nil   // a new message dismisses an unanswered "remember?" prompt
        if msg == "/clear" { runClear(); return }
        if msg == "/compact" { runCompact(); return }
        if msg == "/memory" { runMemoryList(); return }
        if msg.hasPrefix("/remember ") {
            let fact = String(msg.dropFirst("/remember ".count))
            history.append(Turn(role: "human", text: msg))
            Task {
                await Backend.shared.addFact(fact)
                history.append(Turn(role: "ai", text: "Got it — I'll remember that."))
                inputFocused = true
            }
            return
        }
        if msg == "/forget" { runMemoryList(forForget: true); return }
        if msg.hasPrefix("/forget ") {
            let id = String(msg.dropFirst("/forget ".count))
                .trimmingCharacters(in: .whitespaces)
            if id.isEmpty {
                history.append(Turn(role: "ai", text: "Usage: /forget <id>"))
                inputFocused = true
                return
            }
            Task {
                let ok = await Backend.shared.forgetFact(id: id)
                history.append(Turn(role: "ai",
                    text: ok ? "Forgotten." : "No fact with that id."))
                inputFocused = true
            }
            return
        }
        history.append(Turn(role: "human", text: msg))
        Task { await route(msg) }
    }

    private func route(_ msg: String) async {
        busy = true
        let decision = await Backend.shared.route(msg)
        if decision == "control" {
            CommandBar.shared.isRunningControl = true
            liveActivity = "Working on it…"
            await Backend.shared.runControlInBar(msg) { ev in
                let type = ev["type"] as? String
                if type == "tool_call" {
                    let tool = ev["tool_name"] as? String ?? ""
                    liveActivity = "Working on it — \(Self.verbMap[tool] ?? tool)…"
                } else if type == "done" {
                    let content = ev["content"] as? String ?? "Done."
                    history.append(Turn(role: "ai", text: content))
                    liveActivity = nil
                } else if type == "error" {
                    let content = ev["content"] as? String ?? "Failed."
                    history.append(Turn(role: "error", text: content))
                    liveActivity = nil
                }
            }
            liveActivity = nil
            CommandBar.shared.isRunningControl = false
        } else {
            liveActivity = "Thinking…"
            let (reply, badge, capture) = await Backend.shared.chat(msg)
            history.append(Turn(role: "ai", text: reply))
            ctxBadge = badge
            liveActivity = nil
            if askBeforeRemember, let capture = capture, !capture.isEmpty {
                pendingCapture = capture
            }
        }
        busy = false
        inputFocused = true   // persistent focus after every response
    }

    private func loadStatus() {
        Task { ctxBadge = await Backend.shared.status().badge }
        Task {
            let provider = await Backend.shared.currentProvider()
            let model = await Backend.shared.currentModel()
            modelLabel = model.isEmpty ? provider : "\(provider) · \(model)"
        }
    }

    private func runClear() {
        Task {
            _ = await Backend.shared.clear()
            history = []
            ctxBadge = await Backend.shared.status().badge
            inputFocused = true
        }
    }

    private func runCompact() {
        Task { ctxBadge = await Backend.shared.compact(); inputFocused = true }
    }

    private func runMemoryList(forForget: Bool = false) {
        Task {
            let facts = await Backend.shared.facts()
            if facts.isEmpty {
                history.append(Turn(role: "ai",
                    text: "I don't know anything about you yet. Tell me, or use /remember <fact>."))
            } else {
                let lines = facts.map { f in
                    forForget ? "• [\(f.id)] \(f.text)" : "• \(f.text) (\(f.section))"
                }.joined(separator: "\n")
                let hint = forForget ? "\n\nRemove one with: /forget <id>" : ""
                history.append(Turn(role: "ai", text: "What I know:\n\(lines)\(hint)"))
            }
            inputFocused = true
        }
    }
}
