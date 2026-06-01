import AppKit
import ApplicationServices
import SwiftUI

@MainActor
enum FirstRun {
    private static var window: NSWindow?

    static func runIfNeeded() {
        let axOK = AXIsProcessTrusted()
        let hasProvider = UserDefaults.standard.bool(forKey: "yuki.providerConfigured")
        if axOK && hasProvider { return }
        showWindow()
    }

    static func showWindow() {
        if window != nil { return }
        let w = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 440),
            styleMask: [.titled, .closable],
            backing: .buffered, defer: false)
        w.title = "Welcome to Yuki"
        w.center()
        w.contentView = NSHostingView(rootView: FirstRunView(window: w))
        w.isReleasedWhenClosed = false
        window = w
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    static func openAccessibilitySettings() {
        let url = URL(string:
          "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!
        NSWorkspace.shared.open(url)
    }
}

struct FirstRunView: View {
    let window: NSWindow
    @State private var axGranted = AXIsProcessTrusted()
    @State private var provider = "google"
    @State private var apiKey = ""
    @State private var testResult = ""
    @State private var testing = false

    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Welcome to Yuki").font(.title.bold())

            GroupBox("1. Accessibility permission") {
                HStack {
                    Image(systemName: axGranted ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(axGranted ? .green : .secondary)
                    Text(axGranted
                         ? "Granted"
                         : "Yuki needs Accessibility to drive your apps")
                    Spacer()
                    if !axGranted {
                        Button("Open Settings") {
                            FirstRun.openAccessibilitySettings()
                        }
                    }
                }
                .padding(6)
            }

            GroupBox("2. Choose how Yuki thinks") {
                VStack(alignment: .leading, spacing: 8) {
                    Picker("Provider", selection: $provider) {
                        Text("Google Gemini (free tier)").tag("google")
                        Text("Anthropic Claude").tag("anthropic")
                        Text("Local (Ollama)").tag("ollama")
                    }
                    .pickerStyle(.radioGroup)

                    if provider != "ollama" {
                        SecureField("API key", text: $apiKey)
                            .textFieldStyle(.roundedBorder)
                        Link("Get a key", destination: URL(string:
                            provider == "google"
                            ? "https://aistudio.google.com/apikey"
                            : "https://console.anthropic.com/settings/keys")!)
                            .font(.caption)
                    }

                    HStack {
                        Button(testing ? "Testing…" : "Test connection") { test() }
                            .disabled(testing)
                        Text(testResult).font(.caption)
                    }
                }
                .padding(6)
            }

            Spacer()
            HStack {
                Spacer()
                Button("Finish") { finish() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(!axGranted)
            }
        }
        .padding(24)
        .frame(width: 520, height: 440)
        .onReceive(timer) { _ in axGranted = AXIsProcessTrusted() }
    }

    private func saveKeyIfPresent() {
        if provider != "ollama" && !apiKey.isEmpty {
            Keychain.set(apiKey, account: provider)
        }
    }

    private func test() {
        testing = true
        testResult = ""
        saveKeyIfPresent()
        Task {
            await Backend.shared.saveProvider(provider)
            let ok = await Backend.shared.testConnection()
            testResult = ok ? "✓ Connected" : "✗ Failed — check key"
            testing = false
        }
    }

    private func finish() {
        saveKeyIfPresent()
        Task {
            await Backend.shared.saveProvider(provider)
            UserDefaults.standard.set(true, forKey: "yuki.providerConfigured")
            window.close()
        }
    }
}
