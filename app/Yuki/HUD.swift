import AppKit
import SwiftUI

@MainActor
final class HUD: ObservableObject {
    static let shared = HUD()
    private var panel: NSPanel?

    @Published var line = ""
    @Published var state: State = .idle
    @Published var queuedPreview: String? = nil
    enum State: Equatable { case idle, running, success, failure }

    private static let verbMap: [String: String] = [
        "app_tool": "Switching to", "click_tool": "Clicking",
        "type_tool": "Typing", "shortcut_tool": "Pressing",
        "shell_tool": "Running", "scroll_tool": "Scrolling",
        "scrape_tool": "Reading", "wait_tool": "Waiting",
        "list_app_notes": "Checking app notes", "read_app_note": "Reading guidance",
    ]

    func begin(task: String) {
        state = .running
        line = "Starting…"
        show()
    }

    func setQueued(preview: String) { queuedPreview = preview }
    func clearQueued() { queuedPreview = nil }

    func handle(event o: [String: Any]) {
        guard let type = o["type"] as? String else { return }
        switch type {
        case "tool_call":
            let tool = o["tool_name"] as? String ?? ""
            let verb = Self.verbMap[tool] ?? tool
            line = verb
        case "done":
            state = .success
            let content = (o["content"] as? String ?? "Done")
            line = String(content.prefix(120))
            fadeAfter(5)
        case "error":
            state = .failure
            line = o["error"] as? String ?? "Failed"
            // sticky — no auto-fade
        default:
            break
        }
    }

    private func show() {
        if panel == nil { build() }
        position()
        panel?.orderFront(nil)
    }

    private func fadeAfter(_ secs: Double) {
        Task {
            try? await Task.sleep(nanoseconds: UInt64(secs * 1_000_000_000))
            if state == .success {
                panel?.orderOut(nil)
                state = .idle
            }
        }
    }

    private func build() {
        let p = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 300, height: 80),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered, defer: false)
        p.level = .floating
        p.isOpaque = false
        p.backgroundColor = .clear
        p.hasShadow = true
        p.contentView = NSHostingView(rootView: HUDView(hud: self))
        panel = p
    }

    private func position() {
        guard let p = panel, let s = NSScreen.main else { return }
        let f = s.visibleFrame
        let corner = UserDefaults.standard.string(forKey: "yuki.hudCorner") ?? "top-right"
        let m: CGFloat = 16
        let w: CGFloat = 300
        let h: CGFloat = 80
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
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 10) {
                icon
                Text(hud.line).font(.callout).lineLimit(2)
                Spacer()
            }
            if let next = hud.queuedPreview {
                Text("next: \(next)").font(.caption2).foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(12)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
        .frame(width: 300)
    }

    @ViewBuilder private var icon: some View {
        switch hud.state {
        case .running: ProgressView().controlSize(.small)
        case .success: Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
        case .failure: Image(systemName: "xmark.circle.fill").foregroundStyle(.red)
        case .idle: EmptyView()
        }
    }
}
