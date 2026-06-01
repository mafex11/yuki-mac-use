import AppKit
import SwiftUI

/// A borderless panel that can still become the key window (so its text field
/// can receive keystrokes) and dismisses on Escape.
final class KeyablePanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }

    override func cancelOperation(_ sender: Any?) {
        // Esc closes the command bar.
        orderOut(nil)
    }
}

@MainActor
final class CommandBar {
    static let shared = CommandBar()
    private var panel: NSPanel?

    static let focusRequest = Notification.Name("yuki.commandbar.focus")

    func toggle() {
        if let p = panel, p.isVisible {
            p.orderOut(nil)
            return
        }
        if panel == nil { build() }
        position()
        NSApp.activate(ignoringOtherApps: true)
        panel?.makeKeyAndOrderFront(nil)
        // Re-request text-field focus on every open (onAppear only fires once
        // because the panel/host view is reused across toggles).
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
            NotificationCenter.default.post(name: Self.focusRequest, object: nil)
        }
    }

    func close() { panel?.orderOut(nil) }

    private func build() {
        let p = KeyablePanel(
            contentRect: NSRect(x: 0, y: 0, width: 720, height: 120),
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
        let x = f.midX - 360
        let y = f.maxY - f.height * 0.30
        p.setFrameOrigin(NSPoint(x: x, y: y))
    }
}

struct CommandBarView: View {
    @State private var input = ""
    @State private var history: [Turn] = []
    @State private var ctxBadge = ""
    @State private var busy = false
    @FocusState private var inputFocused: Bool

    struct Turn: Identifiable {
        let id = UUID()
        let role: String   // "human" | "ai"
        let text: String
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("yuki").font(.headline).foregroundStyle(.secondary)
                Spacer()
                Text(ctxBadge).font(.caption).foregroundStyle(.tertiary)
            }
            if !history.isEmpty {
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(history) { turn in
                            Text(turn.role == "human" ? "> \(turn.text)" : turn.text)
                                .font(.callout)
                                .foregroundStyle(turn.role == "human"
                                                 ? .primary : .secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                .frame(maxHeight: 200)
            }
            TextField("Ask Yuki…", text: $input)
                .textFieldStyle(.plain)
                .font(.title3)
                .disabled(busy)
                .focused($inputFocused)
                .onSubmit { submit() }
        }
        .padding(16)
        .frame(width: 720)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
        .onAppear {
            loadStatus()
            inputFocused = true
        }
        .onReceive(NotificationCenter.default.publisher(
            for: CommandBar.focusRequest)) { _ in
            inputFocused = true
        }
    }

    private func submit() {
        let msg = input.trimmingCharacters(in: .whitespaces)
        guard !msg.isEmpty, !busy else { return }
        input = ""
        if msg == "/clear" { runClear(); return }
        if msg == "/compact" { runCompact(); return }
        history.append(Turn(role: "human", text: msg))
        Task { await route(msg) }
    }

    private func route(_ msg: String) async {
        busy = true
        defer { busy = false }
        let decision = await Backend.shared.route(msg)
        if decision == "control" {
            CommandBar.shared.close()
            Backend.shared.enqueueControl(msg)
        } else {
            let (reply, badge) = await Backend.shared.chat(msg)
            history.append(Turn(role: "ai", text: reply))
            ctxBadge = badge
        }
    }

    private func loadStatus() {
        Task {
            let st = await Backend.shared.status()
            ctxBadge = st.badge
        }
    }

    private func runClear() {
        Task {
            _ = await Backend.shared.clear()
            history = []
            let st = await Backend.shared.status()
            ctxBadge = st.badge
        }
    }

    private func runCompact() {
        Task {
            let badge = await Backend.shared.compact()
            ctxBadge = badge
        }
    }
}
