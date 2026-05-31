# Yuki Production Mac App — Design Spec

**Status:** Draft
**Date:** 2026-05-31
**Supersedes:** the dev setup of running `python -m yuki.backend.cli` + `python -m yuki.backend.chat_cli` in two terminals.

---

## 1. Goal

Ship Yuki as a polished, production-grade Mac app that a non-technical macOS
user can install with a single command and use without ever opening a terminal.

The user's mental model is Raycast: press a hotkey, type what you want, get
results in a corner overlay. There is no "backend", no "frontend", no port,
no `.env` file. There is a Mac app called Yuki, and it works.

---

## 2. Target experience

```
$ brew install --cask mafex11/tap/yuki      # 5s download
$ open /Applications/Yuki.app                # right-click → Open first time

(first run)
┌─────────────────────────────────────────────────────────┐
│  Welcome to Yuki                                        │
│  ─────────────────────────────────────────────────────  │
│  Yuki needs two macOS permissions to drive your apps:   │
│                                                         │
│  ☐  Accessibility       [ Open Settings ]              │
│  ☐  Screen Recording    [ Open Settings ]              │
│                                                         │
│  Yuki will continue when both are granted.             │
└─────────────────────────────────────────────────────────┘

(after permissions granted)
✓ Yuki is ready. Press ⌘⇧A from anywhere.
```

Subsequent invocations:

```
⌘⇧A pressed anywhere on macOS
        ▼
┌──────────────────────────────────────────────────────┐
│  yuki                                                │
│  ──────────────────────────────────────────────────  │
│  > what's the capital of france                      │
│    Paris.                                  [ctx 1%]  │
│                                                      │
│  > open whatsapp and message saran                   │
│  ┌────────────────────────────────────────────────┐  │
│  │ Ask Yuki                                  ⏎    │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
        ▼ user hits Enter, panel collapses
        ▼ classifier picks /control
        ▼ HUD pill appears in user's preferred corner

                                        ┌──────────────────┐
                                        │ ◐  Switching to  │
                                        │ WhatsApp         │
                                        └──────────────────┘
                                                ▼
                                        ┌──────────────────┐
                                        │ ◐  Typing message│
                                        └──────────────────┘
                                                ▼
                                        ┌──────────────────┐
                                        │ ✓  Sent to Saran │  ← fades after 5s
                                        └──────────────────┘
```

---

## 3. Architecture

### 3.1 One process tree, two languages

```
Yuki.app process tree
├── Yuki                        ← Swift parent (NSApplication)
│   ├── Menu-bar icon                   (NSStatusItem)
│   ├── Global hotkey handler           (Cmd+Shift+A → CommandBar)
│   ├── CommandBar window               (NSPanel, frosted, borderless)
│   ├── HUD pill window                 (NSPanel, corner-pinned)
│   ├── Permissions assistant           (first-run sheet)
│   └── BackendController               (spawns Python child)
└── Yuki Helper (Python)        ← Python child via Popen
    ├── FastAPI app on Unix Domain Socket
    │   at ~/Library/Application Support/Yuki/yuki.sock
    ├── Existing routers: /chat, /chat/control, /chat/compact,
    │                     /chat/clear, /chat/status, /tools, etc.
    ├── New router: /route          (intent classifier)
    └── Existing yuki/ package (agent, vault, observer, etc.)
```

### 3.2 Inter-process transport: Unix Domain Socket

**No TCP. No localhost ports. No bearer token.**

UDS file lives at `~/Library/Application Support/Yuki/yuki.sock`. File
permissions are `0600` (owner read/write only); only the user that launched
Yuki can connect. macOS firewall never sees a bound port. Activity Monitor's
network tab is empty. macOS 14+ "local network access" prompt is never
triggered.

Swift side uses URLSession with a custom `URLProtocol` for UDS, or libcurl
through Foundation's `URLSession.uploadTask(with:fromFile:)` configured for
UDS. There's a known pattern: build an `httpx.AsyncClient` equivalent in Swift
using `socket(AF_UNIX, SOCK_STREAM, 0)` + `connect(2)` + an HTTP/1.1 framer.
~150 lines, one file. Tested approach used by Tailscale and Docker Desktop.

Python side uses uvicorn's existing `--uds <path>` flag. Single CLI argument
change.

### 3.3 Bundled Python via python-build-standalone

`Yuki.app/Contents/Resources/python/` contains a self-contained Python 3.12
tree from [indygreg/python-build-standalone][pbs]. Includes interpreter,
stdlib, and the entire Yuki dependency tree (FastAPI, anthropic, google-genai,
ollama, tiktoken, pyyaml, etc.) installed via `uv export --frozen`.

[pbs]: https://github.com/indygreg/python-build-standalone

App size budget:
- Python interpreter + stdlib: ~25MB
- Site-packages (LLM SDKs are heavy): ~80MB
- Yuki source: <1MB
- Swift binary + resources: ~5MB
- Total: ~110-150MB

For comparison: Slack 230MB, Cursor 600MB, Raycast 250MB. 150MB is normal.

### 3.4 Lifecycle

| Action | Effect |
|---|---|
| `open Yuki.app` | Swift launches, spawns Python child, waits for UDS readiness, registers hotkey, attaches menu-bar item. No window opens. |
| `⌘⇧A` | CommandBar panel opens. Existing chat history (Plan N) loads inline. |
| User types + Enter | Panel collapses. Classifier routes to `/chat` or `/chat/control`. HUD pill appears. |
| User presses Esc | Panel closes without sending. |
| Click red X on panel | Panel closes. Backend keeps running. |
| Menu-bar → Quit Yuki | Both processes terminate cleanly (SIGTERM to Python child, then exit). |
| User force-quits Yuki | Python child also dies (`prctl(PR_SET_PDEATHSIG)` equivalent: macOS uses `kqueue` watching parent PID; when parent dies, child observes EOF on stdin and exits). |

### 3.5 Storage

```
~/YukiVault/                                    ← user-visible markdown
  00-Identity/  10-People/  20-Projects/  …    (user can edit in Obsidian)

~/Library/Application Support/Yuki/             ← app-internal, hidden
  yuki.sock                                    UDS endpoint (deleted on stop)
  index.db                                     SQLite for observer events
  chat_history.jsonl                           Plan N global history
  trajectories/                                /chat /control raw logs
  app_state.json                               UserDefaults bridge for Python
  python.log                                   Python child stderr (rotated)
  swift.log                                    Swift app log (rotated)
```

Vault is intentionally outside `~/Library/Application Support/` because it's
*user data*, not app data — the user should be able to back it up, edit by
hand, sync to Obsidian, point another tool at it. App-internal junk
(socket, sqlite, logs) belongs in `~/Library`.

---

## 4. UI components

### 4.1 CommandBar (the Raycast panel)

- `NSPanel` with `[.borderless, .nonactivatingPanel]` style
- 720pt wide, dynamic height (input + visible recent history)
- Frosted background via `NSVisualEffectView(material: .hudWindow)`
- Centered horizontally; vertical position = top 30% of main screen
- Floats above all apps (`.floating` window level)
- Cmd+Shift+A toggles open/close globally

Layout:
```
┌─────────────────────────────────────────────────────┐
│  yuki                                  [ctx 24% ▾]  │  ← title + ctx badge
│  ─────────────────────────────────────────────────  │
│  > what time is it                                  │  ← scroll-up history
│    It's 7:42 PM.                                    │
│                                                     │
│  > /clear                                           │
│    History cleared.                                 │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │ Ask Yuki…                                ⏎    │  │  ← input
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

Behavior:
- On open: shows last ~3 turns of `chat_history.jsonl` above the input
- Up-arrow cycles through recent prompts (terminal-style)
- Enter → POST to `/route`, then to `/chat` or `/chat/control` based on
  classifier's response; panel collapses immediately for `/control`, stays
  open and shows reply for `/chat`
- Ctx badge in title is a click-target → opens menu with "Compact",
  "Clear history", "Settings…"
- Esc closes without sending

### 4.2 HUD pill (the corner overlay)

- `NSPanel` with `[.borderless, .nonactivatingPanel, .hudWindow]`
- ~280pt wide, dynamic height (1-3 lines)
- Pinned to user-configurable corner (default top-right, below menu bar)
- Floats above all apps
- Click-through disabled (user can click to expand)

States:

| State | Visual | Auto-fade |
|---|---|---|
| Running | spinner + last tool-call summary, e.g. "◐  Switching to Chrome" | no fade while running |
| Success | green check + final answer, "✓  Sent to Saran" | 5s |
| Failure | red X + failure mode + "click for details", "✕  Step limit reached" | sticky until user clicks/dismisses |
| Queued | hourglass + "next: open notion…" | shown only when a task is waiting |

Click HUD when running → expands into full transcript window (essentially the
CommandBar in scroll-back mode).

User configures corner in Settings (top-right, top-left, bottom-right,
bottom-left). Stored in `UserDefaults.standard["yuki.hudCorner"]`.

### 4.3 Menu-bar icon

```
●  Yuki
─────────────────────
Open command bar    ⌘⇧A
Open transcript     ⌘⇧T
─────────────────────
Compact context
Clear history
─────────────────────
Settings…
─────────────────────
Quit Yuki           ⌘Q
```

- Icon is a small "Y" glyph, monochrome (template image)
- Animates while a `/control` task runs (e.g. dotted spinner)

### 4.4 Settings window

Tabs:

1. **General** — launch on login, hotkey customization, HUD corner, default
   provider/model, vault path override.
2. **Permissions** — live status of Accessibility + Screen Recording, with
   "Open System Settings" buttons.
3. **About** — version, "Check for updates", links to GitHub + docs.

Settings persist via `UserDefaults`; Python reads them through a shim file
at `~/Library/Application Support/Yuki/app_state.json` that the Swift side
writes whenever a relevant default changes.

### 4.5 First-run permissions assistant

A modal sheet on first launch (or whenever required perms are missing).

- Polls `AXIsProcessTrustedWithOptions(nil)` for Accessibility every 1s.
- For Screen Recording: `CGPreflightScreenCaptureAccess()`. (Note: even
  though we don't take screenshots, Screen Recording is needed to read
  window titles via `CGWindowListCopyWindowInfo` in some contexts. If we
  confirm we don't need it, drop this entirely.)
- Each row has [Open Settings] which deep-links via:
  `x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility`
- Once both are granted, the sheet auto-dismisses with a 1s success
  animation, then surfaces the "Press ⌘⇧A" tip.

---

## 5. Backend additions

### 5.1 New endpoint: `POST /route`

Tiny pre-flight classifier the CommandBar hits before deciding which
endpoint to use.

**Request:**
```json
{ "message": "open chrome and find me a youtube video" }
```

**Response:**
```json
{
  "route": "control",
  "reason": "user wants to perform actions on their Mac"
}
```

Implementation: one LLM call via `make_llm()` with a tightly-templated prompt
returning `{ "route": "chat" | "control", "reason": "..." }`. Latency ~300ms
on Gemini Flash, ~150ms on local Ollama. Falls back to a heuristic
(action verbs in input → control; everything else → chat) if the LLM call
errors, so the UI never stalls on classifier failure.

### 5.2 Live streaming: agent-event → SSE bridge (KEY TASK)

**Current reality (the gap):** `_stream_control` does
`result = await agent.ainvoke(task=framed)` — one blocking call that runs the
*entire* desktop loop — then yields a single `done` event. The agent's
per-step events (`THOUGHT`, `TOOL_CALL`, `TOOL_RESULT`, `PLAN`, `EVALUATE`)
are emitted to `ConsoleEventSubscriber` (stdout), NOT into the SSE stream.
So today the HUD would jump straight from "running" to "done" with nothing
in between.

**The fix — a queue-backed event subscriber:**

```python
# yuki/backend/event_bridge.py (NEW)
import asyncio
from yuki.agent.events.views import AgentEvent
from yuki.agent.events.subscriber import BaseEventSubscriber

class QueueEventSubscriber(BaseEventSubscriber):
    """Pushes every AgentEvent into an asyncio.Queue the SSE generator drains."""
    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue = queue
        self._loop = asyncio.get_event_loop()

    def invoke(self, event: AgentEvent) -> None:
        # event.emit() may fire from a worker thread; hop back to the loop.
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
```

`_stream_control` becomes:

```python
queue: asyncio.Queue = asyncio.Queue()
agent = Agent(llm=llm, event_subscriber=QueueEventSubscriber(queue))

# Run the blocking loop as a background task...
task = asyncio.create_task(agent.ainvoke(task=framed))

# ...and drain events as they arrive, yielding each as SSE.
while True:
    try:
        ev = await asyncio.wait_for(queue.get(), timeout=0.25)
        yield _event_to_sse(ev)          # tool_call / tool_result / plan / ...
    except asyncio.TimeoutError:
        if task.done():
            break
result = await task
yield {"type": "done", "content": result.content}
```

**Threading caveat:** the agent's loop runs sync tool calls; `event.emit()`
may fire from a thread other than the event loop. `call_soon_threadsafe` is
mandatory — a plain `queue.put_nowait` from a worker thread corrupts the loop.
This is the #1 subtle bug to get right.

The SSE event types the HUD consumes:

| Event type | Data | HUD action |
|---|---|---|
| `tool_call` | `{tool_name, params_summary}` | Replace pill text with `"<verb> <noun>"` |
| `tool_result` | `{tool_name, is_success}` | If failure, flash red briefly |
| `evaluate` | `{evaluate}` | Reserved (not currently shown) |
| `plan` | `{plan}` | Reserved (could expose in expanded view) |
| `done` | `{content}` | Pill turns green, shows content, fades 5s |
| `error` | `{error}` | Pill turns red, sticky |

Tool-name → verb mapping is a small table on the Swift side:

```swift
let verbMap = [
    "app_tool": "Switching to",
    "click_tool": "Clicking",
    "type_tool": "Typing",
    "shortcut_tool": "Pressing",
    "shell_tool": "Running",
    "scroll_tool": "Scrolling",
    "scrape_tool": "Reading",
    "wait_tool": "Waiting",
    "list_app_notes": "Checking app notes",
    "read_app_note": "Reading guidance for",
]
```

### 5.3 Task queue

When the user sends a `/control` request while one is in flight, the second
request waits in a FIFO queue. HUD shows "next: <preview>" subtitle.

Implementation: `asyncio.Queue` inside the Python backend, a single
worker task that drains it and calls `Agent.ainvoke` per item. Requests
coming over UDS get a queue slot ID immediately, then stream their SSE
events when their turn comes.

### 5.4 Drop bearer-token auth on UDS

When uvicorn is bound to UDS, the `require_token` dependency becomes a
no-op. UDS file permissions are the boundary. Keep the dependency wired
for backwards-compat with the dev-setup TCP mode (toggled by an env var).

### 5.5 Provider configuration (first-run + Settings)

A fresh install has no API key. `make_llm()` would raise
`ProviderConfigError`. The app MUST onboard a provider before the user can
do anything.

**First-run flow (after permissions are granted):**

```
┌─────────────────────────────────────────────────────────┐
│  Choose how Yuki thinks                                 │
│  ─────────────────────────────────────────────────────  │
│  ● Google Gemini (recommended — free tier)             │
│      API key: [_______________________]  [Get a key ↗] │
│                                                         │
│  ○ Anthropic Claude                                    │
│      API key: [_______________________]               │
│                                                         │
│  ○ Local (Ollama) — private, no key, needs install     │
│      Status: ⚠ Ollama not detected   [Install guide ↗] │
│                                                         │
│                                  [ Test connection ]    │
└─────────────────────────────────────────────────────────┘
```

- "Get a key" deep-links to `https://aistudio.google.com/apikey`.
- "Test connection" sends a 1-token ping via `make_llm()` and shows ✓/✗.
- Stored in `~/Library/Application Support/Yuki/app_state.json`:
  `{ "llm_provider": "google", "llm_model": "gemini-2.5-flash", "google_api_key": "..." }`.
- The key is written to the macOS Keychain (not plaintext json) via the
  Swift side's `Security.framework`; Python reads it back through a tiny
  `/usr/bin/security find-generic-password` shell-out or a keychain binding.
  **Never** store the key in plaintext in the vault or json.

**Backend change:** `yuki/providers/factory.py` currently reads `.env`. Add
a resolution layer that reads `app_state.json` (provider + model) and the
Keychain (api key) when running in bundled-app mode. `.env` remains the
dev-mode fallback.

### 5.6 Ollama handling

If the user picks "Local (Ollama)":

- Yuki cannot bundle Ollama (2GB+ with weights, separate daemon). Detect it:
  `GET http://127.0.0.1:11434/api/tags` — if it answers, Ollama is installed.
- If absent: show "Install guide" deep-linking to ollama.com, plus a
  one-liner `brew install ollama && ollama pull qwen3-vl:8b`.
- Yuki talks to Ollama over its own localhost:11434 (Ollama's port, not
  Yuki's — Yuki itself stays UDS-only). This is the one acceptable network
  hop because it's Ollama's design, not ours.
- Local models are slower and flake on tool-calls; the factory's
  `_UNRELIABLE_TOOL_MODELS` set already warns about this. Surface that
  warning in the UI when a known-weak model is selected.

### 5.7 chat_cli.py — power-user CLI over UDS

`chat_cli.py` is kept and shipped (inside the bundled Python). Reworked to
talk over UDS instead of TCP:

```python
transport = httpx.HTTPTransport(uds=str(history_dir / "yuki.sock"))
client = httpx.Client(transport=transport, base_url="http://yuki")
```

It is NOT surfaced in the GUI. Power users invoke it via:
`/Applications/Yuki.app/Contents/Resources/python/bin/python -m yuki.backend.chat_cli`.
A future `yuki` shell shim (Formula, separate from the Cask) could expose it
as a top-level command — deferred to v0.2.

---

## 6. Build pipeline

### 6.1 release.sh

```bash
#!/usr/bin/env bash
set -euo pipefail

VERSION="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build"
APP="$BUILD/Yuki.app"

# 1. Clean build directory
rm -rf "$BUILD" && mkdir -p "$BUILD"

# 2. Build Swift app
cd "$ROOT/app"
xcodebuild -scheme Yuki \
    -configuration Release \
    -derivedDataPath "$BUILD/derived" \
    archive -archivePath "$BUILD/Yuki.xcarchive"
xcodebuild -exportArchive \
    -archivePath "$BUILD/Yuki.xcarchive" \
    -exportPath "$BUILD" \
    -exportOptionsPlist "$ROOT/app/ExportOptions.plist"

# 3. Bundle Python via python-build-standalone
cd "$ROOT"
PYTHON_VERSION="3.12.7"
PBS_URL="https://github.com/indygreg/python-build-standalone/releases/download/.../cpython-${PYTHON_VERSION}-aarch64-apple-darwin-install_only.tar.gz"
curl -fsSL "$PBS_URL" | tar -xz -C "$BUILD"
mv "$BUILD/python" "$APP/Contents/Resources/python"

# 4. Install yuki + deps into the bundled Python
"$APP/Contents/Resources/python/bin/python3" -m pip install \
    --target "$APP/Contents/Resources/python/lib/python${PYTHON_VERSION%.*}/site-packages" \
    -r "$ROOT/requirements.txt"
cp -R "$ROOT/yuki" "$APP/Contents/Resources/python/lib/python${PYTHON_VERSION%.*}/site-packages/"

# 5. Copy prompts + plist templates
cp -R "$ROOT/yuki/agent/prompt" "$APP/Contents/Resources/prompts"
cp "$ROOT/packaging/launchd/com.yuki.feedback.learner.plist" "$APP/Contents/Resources/launchd/"

# 6. Zip for Cask
cd "$BUILD"
ditto -c -k --keepParent "Yuki.app" "Yuki-${VERSION}.zip"
SHA=$(shasum -a 256 "Yuki-${VERSION}.zip" | cut -d' ' -f1)

# 7. Upload to GitHub Releases
gh release create "v${VERSION}" "Yuki-${VERSION}.zip" \
    --title "Yuki v${VERSION}" \
    --notes "See CHANGELOG.md"

# 8. Bump tap formula
echo "Updating Cask formula..."
cat > "$ROOT/../homebrew-tap/Casks/yuki.rb" <<EOF
cask "yuki" do
  version "${VERSION}"
  sha256 "${SHA}"
  url "https://github.com/mafex11/yuki-mac-use/releases/download/v#{version}/Yuki-#{version}.zip"
  name "Yuki"
  desc "Jarvis-style macOS assistant"
  homepage "https://github.com/mafex11/yuki-mac-use"

  depends_on macos: ">= :ventura"

  app "Yuki.app"

  caveats <<~EOS
    Yuki needs Accessibility permission to drive your Mac.
    On first launch, Yuki will guide you through enabling it
    in System Settings → Privacy & Security → Accessibility.

    Press Cmd+Shift+A from anywhere to open the command bar.
  EOS

  uninstall quit: "com.yuki.app",
            launchctl: "com.yuki.feedback.learner"

  zap trash: [
    "~/Library/Application Support/Yuki",
    "~/Library/LaunchAgents/com.yuki.feedback.learner.plist",
    "~/Library/Preferences/com.yuki.app.plist",
  ]
end
EOF

cd "$ROOT/../homebrew-tap"
git add Casks/yuki.rb
git commit -m "yuki ${VERSION}"
git push

echo "✓ Released yuki ${VERSION}"
```

### 6.2 Cask formula

Lives in user's existing `homebrew-tap/Casks/yuki.rb` (matches the existing
`git-schedule` tap pattern). Auto-updated by `release.sh`.

### 6.3 First version is unsigned

Ship v0.1 unsigned. Users right-click → Open the first time. README includes
a screenshot of the Gatekeeper dialog and the trick. When usage justifies it,
spend $99 on Apple Developer Program and add codesign + notarytool to
release.sh. Cask formula doesn't change; the zip just becomes notarized.

---

## 7. Failure modes and recovery

| Failure | Recovery |
|---|---|
| Python child crashes mid-task | Swift detects via `Process.terminationHandler`, surfaces a red HUD "Backend crashed, restarting…", relaunches. |
| UDS file stale from prior crashed run | On startup, Swift `unlink`s an existing `yuki.sock` before spawning Python. |
| Permissions revoked while running | Swift polls perms every 30s, shows the assistant when missing. |
| User runs second copy of Yuki.app | Swift detects via `NSRunningApplication` enumeration with own bundle ID; if found, brings the existing instance forward and exits. |
| Cmd+Shift+A conflicts with another app | Settings allows hotkey customization. Default checks for conflicts on first launch. |
| Storage full | Vault writes wrapped in try/except; HUD shows "Disk full, fix and retry". |
| Update available | `Sparkle` framework or simple GitHub Releases polling — out of scope for v0.1. |
| No LLM provider configured | First-run onboarding (§5.5) blocks until a provider tests OK. If config is later deleted, CommandBar shows "Configure a provider" with a Settings shortcut. |
| Backend won't start (corrupt python tree) | Swift retries once, then shows a fatal dialog: "Yuki couldn't start its engine. Reinstall via `brew reinstall --cask yuki`." with a "Copy logs" button. |

### 7.1 Auto-start at login

Opt-in, OFF by default. Settings → General → "Launch Yuki at login".

- When enabled: Swift registers the app as a login item via
  `SMAppService.mainApp.register()` (macOS 13+ API; no separate helper
  needed). When disabled: `SMAppService.mainApp.unregister()`.
- This is the *app* auto-starting — distinct from the feedback-learner
  LaunchAgent (§Plan M), which is a scheduled 03:00 job and installs
  separately on first run if the user opts into the observer.
- The observer daemon (`YUKI_OBSERVER=1`) and daily learner only run while
  the backend is alive. So passive learning requires either the app running
  in the foreground or auto-start enabled. The first-run flow explains this:
  "Enable launch-at-login so Yuki can learn your patterns in the background."

### 7.2 Data migration across versions

Each persisted format carries a `schema_version` int:

- `app_state.json` → top-level `"schema_version": 1`
- `chat_history.jsonl` → first line is a header record
  `{"_meta": {"schema_version": 1}}`
- Vault notes already carry frontmatter; add `schema` field if absent.

On startup, Swift passes the app's bundle version to Python via env. Python's
`yuki.migrations` module (NEW) compares stored `schema_version` against the
code's `CURRENT_SCHEMA` and runs ordered migration functions. Migrations are
forward-only, idempotent, and logged. If a migration fails, Python refuses to
start and surfaces the error to Swift (which shows the fatal dialog). Never
silently corrupt user data.

For v0.1 there's nothing to migrate yet — but the version stamping ships now
so v0.2 has something to migrate *from*.

### 7.3 Log visibility

- Python child stderr → `~/Library/Application Support/Yuki/python.log`
  (rotated at 5MB, keep 3).
- Swift app log → `swift.log` same dir.
- Menu-bar → "Help" → "Reveal logs in Finder" opens the directory.
- The fatal-error dialog has a "Copy logs to clipboard" button that bundles
  the tail of both logs — makes bug reports actionable.

---

## 8. Resolved decisions / non-goals for v0.1

**Resolved decisions (this brainstorm):**
- **LLM onboarding:** ask during first-run; Gemini cloud-key default, Anthropic
  or local Ollama as alternatives (§5.5). Keys go in Keychain.
- **Live HUD:** YES — build the agent-event→SSE streaming bridge (§5.2). This
  is a required v0.1 task, not deferred.
- **Auto-start:** opt-in, OFF by default, via `SMAppService` (§7.1).
- **Scope:** ship the full spec (all tasks), not a thin MVP.
- **Hotkey:** Cmd+Shift+A default, user-configurable in Settings. (Only
  conflicts with Finder's "Show Applications" when a Finder window is
  frontmost; acceptable, and customization escape-hatch exists.)
- **API key storage:** macOS Keychain via `Security.framework`. Python reads
  via `security find-generic-password`. No plaintext keys anywhere.
- **Build system:** migrate `app/` from SPM `Package.swift` to a proper
  `.xcodeproj` (needed for Info.plist, entitlements, resource bundling, and
  future notarization). This is Plan O Task 0.

**Non-goals for v0.1:**
- Code signing + notarization. Defer to v0.2 once usage justifies $99/year.
- Auto-update via Sparkle. Defer to v0.2.
- iCloud / multi-device vault sync. Vault is local-only.
- Apple Silicon + Intel universal binary. Apple Silicon only for v0.1.
- Voice activation ("Hey Yuki"). The `Wakeword.swift` skeleton stays
  but is disabled in v0.1.

**Technical risks to verify during implementation:**

1. **UDS in URLSession on macOS.** Verify the Swift path works. If URLSession
   refuses UDS, fall back to `Network.framework` `NWConnection` over
   `NWEndpoint.Unix`. SSE over UDS specifically needs a streaming read loop,
   not `URLSession.data(for:)` (which buffers the whole response). Use
   `URLSession.bytes(for:)` or raw `NWConnection.receive` — confirm the
   chosen transport supports incremental reads, or the HUD won't stream.

2. **tiktoken offline.** tiktoken downloads BPE files on first use. Preload
   `cl100k_base` at build time (set `TIKTOKEN_CACHE_DIR` inside the bundle)
   so the app works offline and air-gapped.

3. **python-build-standalone + native deps.** Some deps ship compiled
   wheels (pydantic-core, tiktoken). Confirm the arm64 wheels match the
   python-build-standalone ABI. Test the bundled tree on a clean Mac with no
   system Python.

4. **Child-process death on parent exit.** macOS has no `PR_SET_PDEATHSIG`.
   Use the kqueue-watch-parent-PID pattern, or have Python poll
   `os.getppid() == 1` (re-parented to launchd = parent died) and self-exit.

---

## 9. Acceptance criteria for v0.1 (production-ready)

1. `brew install --cask mafex11/tap/yuki` works on a fresh Mac.
2. First launch shows permissions assistant; granting both auto-dismisses.
3. ⌘⇧A opens the CommandBar from any app within 200ms of keypress.
4. Plain question (`"what's 2+2"`) → classifier picks `chat` → answer in
   panel within 2s.
5. Action request (`"open whatsapp and message saran hi"`) → classifier
   picks `control` → panel collapses → HUD shows step-by-step → final
   green check.
6. `chat_history.jsonl` persists across app quit/relaunch.
7. `/compact` slash command in CommandBar reduces ctx % visibly.
8. Activity Monitor shows two processes (`Yuki`, `Yuki Helper (Python)`).
   Force-quitting `Yuki` kills the helper within 2s.
9. App size < 200MB.
10. No bound TCP ports (verified via `lsof -iTCP -sTCP:LISTEN`).

---

## 10. Implementation plan summary

Plan O breaks this into 16 tasks, grouped Python-first (so the backend is
testable over UDS before any Swift work), then Swift, then packaging.

**Phase A — Backend (Python, testable via curl --unix-socket):**
1. uvicorn → UDS; `require_token` no-op on UDS, env-gated TCP fallback.
2. Path relocation: app-data → `~/Library/Application Support/Yuki/`, vault
   stays `~/YukiVault/`; `app_state.json` provider/model resolution in
   `make_llm()`; Keychain read for api keys.
3. `POST /route` intent classifier (LLM + heuristic fallback).
4. **Agent-event→SSE bridge** (`QueueEventSubscriber`, `call_soon_threadsafe`,
   background-task drain loop). Keep ConsoleEventSubscriber alongside.
5. Task queue (`asyncio.Queue` + single worker) with "next: …" slot info.
6. Schema versioning + `yuki.migrations` skeleton (no-op for v0.1).
7. `chat_cli.py` over UDS.

**Phase B — Swift app:**
8. UDS HTTP client supporting *streaming* reads (verify SSE works) — the
   transport risk in §8.1.
9. BackendController: spawn bundled Python over UDS, stale-socket cleanup,
   child-death handling, health wait, crash-restart.
10. CommandBar: frosted borderless NSPanel, scroll-up history, ctx badge,
    Enter→/route→collapse-or-stay, Esc, up-arrow history.
11. HUD pill: corner-pinned NSPanel, state machine
    (running/success/failure/queued), verb-mapped tool summaries, fade timers.
12. Settings window: General (login item, hotkey, HUD corner, vault path),
    Provider (the §5.5 onboarding, also reachable post-setup), Permissions,
    About.
13. First-run flow: permissions assistant + provider onboarding + "press ⌘⇧A".
14. Menu-bar refresh: spinner while control runs, Reveal logs, Quit.

**Phase C — Packaging + ship:**
15. `release.sh`: xcodebuild archive + python-build-standalone bundling +
    tiktoken preload + zip + GitHub Release + Cask bump.
16. Cask formula in homebrew-tap; first release; README with Gatekeeper
    screenshot + install instructions.

Each task is TDD where testable (Phase A endpoints, migrations, classifier).
Swift UI tasks are manually verified against the §9 acceptance criteria.

Plan to follow this spec verbatim once approved.
