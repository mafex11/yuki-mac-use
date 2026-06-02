import AppKit
import ServiceManagement
import SwiftUI
import ApplicationServices

@MainActor
enum SettingsWindow {
    private static var window: NSWindow?

    static func show() {
        if window == nil {
            let w = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 620, height: 460),
                styleMask: [.titled, .closable],
                backing: .buffered, defer: false)
            w.title = "Yuki Settings"
            w.center()
            w.contentView = NSHostingView(rootView: SettingsView())
            w.isReleasedWhenClosed = false
            window = w
        }
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}

struct SettingsView: View {
    var body: some View {
        TabView {
            GeneralSettings().tabItem { Label("General", systemImage: "gear") }
            ProviderSettings().tabItem { Label("Provider", systemImage: "brain") }
            PermissionsSettings().tabItem { Label("Permissions", systemImage: "lock") }
            MemorySettings().tabItem { Label("Memory", systemImage: "brain.head.profile") }
            AboutSettings().tabItem { Label("About", systemImage: "info.circle") }
        }
        .frame(width: 620, height: 460)
        .padding()
    }
}

struct GeneralSettings: View {
    @AppStorage("yuki.launchAtLogin") private var launchAtLogin = false
    @AppStorage("yuki.hudCorner") private var hudCorner = "top-right"

    var body: some View {
        Form {
            Toggle("Launch Yuki at login", isOn: $launchAtLogin)
                .onChange(of: launchAtLogin) { on in setLaunchAtLogin(on) }
            Picker("HUD corner", selection: $hudCorner) {
                Text("Top right").tag("top-right")
                Text("Top left").tag("top-left")
                Text("Bottom right").tag("bottom-right")
                Text("Bottom left").tag("bottom-left")
            }
            Text("Hotkey: ⌘⇧A (fixed for v0.1)")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding()
    }

    private func setLaunchAtLogin(_ on: Bool) {
        do {
            if on { try SMAppService.mainApp.register() }
            else { try SMAppService.mainApp.unregister() }
        } catch {
            NSLog("launch-at-login toggle failed: \(error)")
        }
    }
}

struct ProviderSettings: View {
    @State private var provider = "google"
    @State private var apiKey = ""
    @State private var keyAlreadySaved = false
    @State private var testResult = ""
    @State private var testing = false
    @State private var saving = false
    @State private var loaded = false

    // Ollama model selection
    @State private var ollamaModels: [String] = []
    @State private var ollamaModel = ""
    @State private var ollamaRunning = true

    var body: some View {
        Form {
            Picker("Provider", selection: $provider) {
                Text("Google Gemini").tag("google")
                Text("Anthropic Claude").tag("anthropic")
                Text("Local (Ollama)").tag("ollama")
            }
            .onChange(of: provider) { _ in
                guard loaded else { return }
                reloadForProvider()
            }

            if provider == "ollama" {
                ollamaSection
            } else {
                SecureField(keyAlreadySaved
                            ? "API key (saved — leave blank to keep)"
                            : "API key", text: $apiKey)
                if keyAlreadySaved && apiKey.isEmpty {
                    Label("Key saved for \(provider)", systemImage: "checkmark.seal.fill")
                        .font(.caption).foregroundStyle(.green)
                }
            }

            HStack {
                Button(saving ? "Saving…" : "Save") { save() }.disabled(saving)
                Button(testing ? "Testing…" : "Test") { test() }.disabled(testing)
                Text(testResult)
                    .font(.caption)
                    .foregroundStyle(testResult.hasPrefix("✓") ? .green
                                     : testResult.hasPrefix("✗") ? .red : .secondary)
            }
        }
        .padding()
        .onAppear {
            // Reflect the provider/model the backend actually uses, not a
            // local default — so Settings agrees with app_state.json.
            guard !loaded else { return }
            loaded = true
            Task {
                provider = await Backend.shared.currentProvider()
                reloadForProvider()
            }
        }
    }

    @ViewBuilder private var ollamaSection: some View {
        if ollamaRunning && !ollamaModels.isEmpty {
            Picker("Model", selection: $ollamaModel) {
                ForEach(ollamaModels, id: \.self) { m in Text(m).tag(m) }
            }
            .onChange(of: ollamaModel) { m in
                guard loaded, !m.isEmpty else { return }
                Task { await Backend.shared.saveProvider("ollama", model: m) }
            }
        } else {
            Label("Ollama not reachable — start it, then reopen Settings",
                  systemImage: "exclamationmark.triangle")
                .font(.caption).foregroundStyle(.secondary)
            TextField("Model name (e.g. qwen3-vl:8b)", text: $ollamaModel)
                .textFieldStyle(.roundedBorder)
        }
    }

    /// Refresh the key indicator + Ollama models for the selected provider.
    private func reloadForProvider() {
        apiKey = ""
        testResult = ""
        if provider == "ollama" {
            keyAlreadySaved = false
            Task {
                let r = await Backend.shared.ollamaModels()
                ollamaRunning = r.running
                ollamaModels = r.models
                let saved = await Backend.shared.currentModel()
                // Prefer the saved model if it's installed; else first available.
                if r.models.contains(saved) { ollamaModel = saved }
                else if let first = r.models.first { ollamaModel = first }
                else { ollamaModel = saved }
            }
        } else {
            keyAlreadySaved = !Backend.shared.savedKey(for: provider).isEmpty
        }
    }

    /// Persist the current selection. Returns when the write has landed so
    /// callers (Save button, Test) can sequence on it.
    @discardableResult
    private func persist() async -> Bool {
        if provider == "ollama" {
            let m = ollamaModel.trimmingCharacters(in: .whitespaces)
            await Backend.shared.saveProvider("ollama", model: m.isEmpty ? nil : m)
            return true
        }
        if !apiKey.isEmpty {
            Keychain.set(apiKey, account: provider)
            keyAlreadySaved = true
            apiKey = ""
        }
        await Backend.shared.saveProvider(provider)
        await Backend.shared.pushKey(for: provider)
        return true
    }

    private func save() {
        saving = true
        testResult = ""
        Task {
            await persist()
            saving = false
            testResult = "✓ Saved"
            // Clear the confirmation after a moment so it doesn't linger.
            try? await Task.sleep(nanoseconds: 2_500_000_000)
            if testResult == "✓ Saved" { testResult = "" }
        }
    }

    private func test() {
        testing = true
        testResult = ""
        Task {
            await persist()
            let ok = await Backend.shared.testConnection()
            testResult = ok ? "✓ Connected" : "✗ Failed"
            testing = false
        }
    }
}

struct PermissionsSettings: View {
    @State private var axGranted = AXIsProcessTrusted()
    private let timer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        Form {
            HStack {
                Image(systemName: axGranted ? "checkmark.circle.fill" : "xmark.circle")
                    .foregroundStyle(axGranted ? .green : .red)
                Text("Accessibility")
                Spacer()
                Button("Open Settings") {
                    let url = URL(string:
                      "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!
                    NSWorkspace.shared.open(url)
                }
            }
        }
        .padding()
        .onReceive(timer) { _ in axGranted = AXIsProcessTrusted() }
    }
}

struct AboutSettings: View {
    var body: some View {
        VStack(spacing: 12) {
            Text("Yuki").font(.largeTitle.bold())
            Text("v0.1.0").foregroundStyle(.secondary)
            Link("GitHub", destination: URL(string:
                "https://github.com/mafex11/yuki-mac-use")!)
        }
        .padding()
    }
}

struct MemorySettings: View {
    @State private var facts: [Backend.Fact] = []
    @State private var newFact = ""
    @State private var learner = true
    @State private var ask = true
    @State private var loaded = false
    @State private var didLoad = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("What Yuki knows about you").font(.headline)

            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(facts) { fact in
                        FactRow(fact: fact) {
                            Task {
                                await Backend.shared.forgetFact(id: fact.id)
                                await reload()
                            }
                        }
                        Divider()
                    }
                    if facts.isEmpty {
                        Text("Nothing yet. Add a fact below, or just tell Yuki about yourself in chat.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            .frame(maxHeight: 200)

            HStack {
                TextField("Add a fact (e.g. I use Linear for tickets)", text: $newFact)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { addFact() }
                Button("Add") { addFact() }
                    .disabled(newFact.trimmingCharacters(in: .whitespaces).isEmpty)
            }

            Divider()
            Toggle("Daily learning (distill tasks into reusable notes)", isOn: $learner)
                .onChange(of: learner) { on in
                    guard didLoad else { return }
                    Task {
                        await Backend.shared.setMemorySettings(learner: on)
                        LaunchAgentManager.reconcile(enabled: on)
                    }
                }
            Toggle("Ask before remembering things from chat", isOn: $ask)
                .onChange(of: ask) { on in
                    guard didLoad else { return }
                    Task { await Backend.shared.setMemorySettings(ask: on) }
                }
        }
        .padding()
        .onAppear {
            guard !loaded else { return }
            loaded = true
            Task {
                let s = await Backend.shared.memorySettings()
                learner = s.learner
                ask = s.ask
                didLoad = true
                await reload()
            }
        }
    }

    private func addFact() {
        let text = newFact.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        newFact = ""
        Task {
            await Backend.shared.addFact(text)
            await reload()
        }
    }

    private func reload() async { facts = await Backend.shared.facts() }
}

/// One fact row: section chip + text truncated to 4 lines with a Show
/// more/less toggle, plus a delete button.
struct FactRow: View {
    let fact: Backend.Fact
    let onDelete: () -> Void
    @State private var expanded = false

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text(fact.section.uppercased())
                .font(.caption2).foregroundStyle(.secondary)
                .frame(width: 64, alignment: .leading)
            VStack(alignment: .leading, spacing: 2) {
                Text(fact.text)
                    .font(.callout)
                    .lineLimit(expanded ? nil : 4)
                    .textSelection(.enabled)
                // Only offer expand when the text is long enough to be clipped.
                if fact.text.count > 200 {
                    Button(expanded ? "Show less" : "Show more") { expanded.toggle() }
                        .font(.caption2)
                        .buttonStyle(.borderless)
                }
            }
            Spacer()
            Button(role: .destructive, action: onDelete) {
                Image(systemName: "minus.circle")
            }
            .buttonStyle(.borderless)
        }
    }
}
