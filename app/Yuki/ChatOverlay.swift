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
                backing: .buffered, defer: false
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
