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
                contentRect: NSRect(x: 0, y: 0, width: 480, height: 420),
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
        .frame(width: 480, height: 420)
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
    @State private var testResult = ""
    @State private var testing = false
    @State private var loaded = false

    var body: some View {
        Form {
            Picker("Provider", selection: $provider) {
                Text("Google Gemini").tag("google")
                Text("Anthropic Claude").tag("anthropic")
                Text("Local (Ollama)").tag("ollama")
            }
            if provider != "ollama" {
                SecureField("API key (leave blank to keep existing)", text: $apiKey)
            }
            HStack {
                Button("Save") { save() }
                Button(testing ? "Testing…" : "Test") { test() }.disabled(testing)
                Text(testResult).font(.caption)
            }
        }
        .padding()
        .onAppear {
            // Reflect the provider the backend actually uses, not a local
            // default — so Settings agrees with first-run + app_state.json.
            guard !loaded else { return }
            loaded = true
            Task { provider = await Backend.shared.currentProvider() }
        }
    }

    private func save() {
        if provider != "ollama" && !apiKey.isEmpty {
            Keychain.set(apiKey, account: provider)
        }
        Task {
            await Backend.shared.saveProvider(provider)
            await Backend.shared.pushKey(for: provider)
        }
    }

    private func test() {
        testing = true
        save()
        Task {
            // Give saveProvider + pushKey a beat to land before testing.
            try? await Task.sleep(nanoseconds: 200_000_000)
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
                        HStack(alignment: .top) {
                            Text(fact.section.uppercased())
                                .font(.caption2).foregroundStyle(.secondary)
                                .frame(width: 64, alignment: .leading)
                            Text(fact.text).font(.callout)
                            Spacer()
                            Button(role: .destructive) {
                                Task {
                                    await Backend.shared.forgetFact(id: fact.id)
                                    await reload()
                                }
                            } label: { Image(systemName: "minus.circle") }
                                .buttonStyle(.borderless)
                        }
                    }
                    if facts.isEmpty {
                        Text("Nothing yet. Add a fact below, or just tell Yuki about yourself in chat.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            .frame(maxHeight: 160)

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
