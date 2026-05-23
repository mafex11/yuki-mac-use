# Yuki for macOS — Design Spec

**Date:** 2026-05-22
**Status:** Design approved, ready for implementation planning
**Author:** Sudhanshu Pandit

---

## 1. Vision

A downloadable macOS app that lets the user control their Mac with natural language. The user's hands never have to touch keyboard or mouse for routine tasks. Yuki knows *who the user is* before they type the first command, because on first run it builds a personal knowledge base — an Obsidian-compatible markdown vault — by scanning the user's calendars, contacts, apps, files, and activity. From that foundation it then watches the user passively over time, learning routines and patterns, and grows progressively more capable of acting on the user's behalf.

**The differentiator** is the memory layer. Other computer-use agents start each session blank and stay blank. Yuki starts knowing the user and gets sharper with use.

**Distribution model:** one signed `.dmg`, double-click to install, ~8-12 minutes from download to a working assistant that knows them. No Python install. No Terminal. No Obsidian dependency. No SaaS. BYO LLM API key, Claude-first.

---

## 2. Foundation Decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Agent core | Fork [MacOS-Use](https://github.com/CursorTouch/MacOS-Use) MIT | ~7000 lines of working PyObjC AX bindings, 13 LLM providers, prompt caching, loop guards. Don't reinvent the engine — differentiate above it. |
| App shape | SwiftUI menu-bar app + embedded Python backend + local Next.js UI | Native presence + rich web frontend without Electron weight. |
| LLM | BYO API key, Claude-first | Zero server cost to operate, zero LLM-side privacy concern, 13 providers available as alternates. |
| Invocation | Global hotkey + opt-in wakeword + menu-bar | All three, user-toggleable. |
| Memory seed | Guided onboarding scan | 5–10 min scan produces seed vault. Scanner does not run again. |
| Memory format | Visible markdown vault at `~/YukiVault/` + SQLite index | User-owned files, transparent, hand-editable, rebuildable index. Obsidian compatible by accident, never required. |
| Observation | Window titles + URLs + app focus | Macroscopic workflow, no content scraping, no OCR by default. |
| Episodes | Daily review nudge | Lets user catch misinterpretations before they cement. |
| Confirmation | Always ask, with two escape valves | Trusted routines + burst mode prevent claustrophobia. |
| Trigger creation | Compactor-suggested + user-defined | Patterns are earned by behavior or words; no hardcoded starter set. |
| Deviation alerts | Conservative — 4–5 specific kinds | Avoids "why is Yuki nagging me." |
| Mute UX | Quick presets + per-trigger-type toggles | Two layers: menu-bar quick mute + Settings categorical kill switches. |
| v1 tool scope | Full set (15 native tools) | Messages and Meeting tools behind feature flag if not stable by RC1. |
| Tool extensibility | Public `@tool` SDK at v1 with hot-reload from `~/.yuki/tools/` | Raycast Extensions taught us this is a wedge feature, not a v1.1 polish item. The registry is small; we expose it. |
| Build tool | Briefcase (BeeWare) | Purpose-built for shipping Python as native Mac apps with signing/notarization. |
| Distribution | GitHub Releases + Homebrew Cask at launch | Free, signed, no review process, two channels covers casual + technical users. |
| Telemetry | Zero, ever | Privacy is the pitch. "Export diagnostics" button for manual bug reports. |

---

## 3. System Architecture

### 3.1 Process Model

```
Yuki.app  (one bundled application, one signed .dmg)
    │
    ├── Menu-bar process  (Swift / SwiftUI)
    │       • Always-on icon, status, mute, quit
    │       • Owns lifecycle of child processes
    │       • Talks to Python backend via local HTTP + SSE
    │       • Hosts the global hotkey + wakeword listener
    │
    ├── Python backend  (FastAPI on 127.0.0.1:<random-port>, loopback only)
    │       • Agent core (forked MacOS-Use)
    │       • Memory subsystem (vault read/write, indexer, retrieval)
    │       • Observer daemon (event stream)
    │       • Trigger engine
    │       • Native tool implementations
    │
    └── Frontend  (Next.js static export, served by FastAPI)
            • Chat UI, settings, memory browser, trigger manager
            • Opens in default browser on demand (⌘⇧Y)
            • Ported from Yuki/LLM-OS Next.js shell

Two LaunchAgents installed on first run (with user permission):
    com.yuki.agent.plist        → launches Yuki on login, restarts on crash
    com.yuki.scheduler.plist    → executes scheduled tasks even if menu-bar UI is quit
```

Auth between menu-bar and backend: per-launch random token bound to loopback. Frontend gets the token via the URL when opened from the menu bar.

### 3.2 Module Layout

```
yuki/
├── app/
│   ├── menubar/             # Swift sources for the menu-bar app
│   ├── icons/
│   └── Info.plist
├── backend/
│   ├── server.py            # FastAPI; routers below
│   ├── routers/
│   │   ├── chat.py          # /chat (SSE stream)
│   │   ├── memory.py        # /memory/* (read, search, write)
│   │   ├── triggers.py      # /triggers/* (CRUD, audit log)
│   │   ├── settings.py      # /settings/* (get/set, validates keys)
│   │   ├── scan.py          # /scan/* (onboarding pipeline)
│   │   └── tools.py         # /tools (list capabilities, danger levels)
│   └── auth.py
├── agent/                   # forked from MacOS-Use, then evolved
│   ├── service.py           # main loop
│   ├── loop.py              # LoopGuard
│   ├── context/             # prompt assembly with vault hot-context injection
│   ├── desktop/             # screenshot, app management
│   ├── tree/                # accessibility tree
│   ├── watchdog/
│   ├── events/
│   └── prompt/
│       ├── system.md        # rewritten for Yuki + macOS-native preference rule
│       └── human.md
├── ax/                      # MacOS-Use's PyObjC bindings, vendored
├── memory/
│   ├── vault.py             # markdown read/write, frontmatter parser
│   ├── indexer.py           # embeddings → SQLite + sqlite-vec
│   ├── retriever.py         # search interface used by memory_* tools
│   └── schemas.py           # Pydantic models for note frontmatter
├── observer/
│   ├── daemon.py            # asyncio supervisor for all event sources
│   ├── sources/
│   │   ├── workspace.py     # NSWorkspace app focus
│   │   ├── window.py        # AX focused-window
│   │   ├── browser.py       # Chrome/Safari URL via AppleScript
│   │   ├── idle.py          # CGEventSource idle time
│   │   ├── calendar.py      # EventKit observer
│   │   ├── filesystem.py    # FSEvents
│   │   ├── power.py         # IOKit
│   │   └── network.py       # CWInterface
│   ├── ringbuffer.py        # in-memory 24h ring
│   └── persistence.py       # 60s flush to SQLite events table
├── episodist/
│   ├── builder.py           # daily episode assembler
│   └── compactor.py         # weekly pattern → vault diff
├── triggers/
│   ├── engine.py            # asyncio match + fire loop
│   ├── conditions/          # one module per condition kind
│   │   ├── time.py
│   │   ├── calendar.py
│   │   ├── app_state.py
│   │   ├── idle.py
│   │   ├── deviation.py
│   │   └── external.py
│   ├── presenter.py         # menu-bar / notification / modal routing
│   └── audit.py             # logs to YukiVault/60-Episodes/triggers-*.md
├── scan/                    # onboarding (one-time) collectors
│   ├── runner.py
│   ├── collectors/
│   │   ├── system.py
│   │   ├── apps.py
│   │   ├── screen_time.py
│   │   ├── calendar.py
│   │   ├── contacts.py
│   │   ├── mail.py
│   │   ├── files.py
│   │   ├── git.py
│   │   ├── browser.py
│   │   └── shell.py
│   ├── normalizer.py        # raw rows → unified Fact tuples
│   ├── patterns.py          # Fact[] → Entity[] (rule-based clustering)
│   └── notewriter.py        # Entity → markdown via Jinja templates (+ optional LLM polish)
├── tools/
│   ├── base.py              # @tool decorator, danger levels
│   ├── ui/                  # MacOS-Use inherited (click, type, scroll, etc.)
│   ├── native/              # 15 new ones — see §6
│   └── memory/              # memory_search, memory_read, memory_write
├── safety/
│   ├── danger.py            # tool danger classification
│   ├── confirm.py           # ask flow + trusted-routine logic
│   └── audit.py
├── frontend/                # Next.js source
└── packaging/
    ├── briefcase.toml
    ├── notarize.sh
    ├── sparkle/             # appcast.xml template, dsa keys
    └── homebrew/            # cask formula
```

### 3.3 Data Flow at Runtime

```
User input ──► hotkey/voice/menu ──► /chat ──► agent.service.invoke()
                                                       │
                          ┌────────────────────────────┼──────────────────────────┐
                          ▼                            ▼                          ▼
                  Build prompt context           Run tool loop              Stream tokens
                  ─ system prompt                ─ memory tools             back to UI via SSE
                  ─ vault hot-context            ─ native tools
                  ─ recent episode summary       ─ UI fallback tools
                  ─ active window state          ─ each gated by safety
                  ─ user task                       ↓
                                              user confirms
                                                  ↓
                                              tool executes
                                                  ↓
                                              result → next iteration
```

In parallel and continuously:

```
Observer daemon ──► Ring buffer ──► SQLite events (60s flush)
                                        │
                                        ├─► Trigger engine (live match)
                                        │       │
                                        │       └─► Suggestion → user
                                        │
                                        └─► (3am) Episodist → daily episode .md
                                                    │
                                                    └─► (Sundays) Compactor → vault diff
                                                                                  │
                                                                                  └─► 90-Inbox/ for review
```

---

## 4. The Memory Vault

### 4.1 On-Disk Layout

```
~/YukiVault/
├── 00-Identity/
│   ├── Profile.md
│   ├── Preferences.md
│   └── Communication-Style.md
├── 10-People/
│   └── <Name>.md                    # one per frequent contact
├── 20-Projects/
│   └── <Project>.md
├── 30-Routines/
│   ├── Morning.md
│   ├── Standup.md
│   ├── Deep-Work.md
│   └── triggers/
│       └── <trigger-id>.md          # see §5.4
├── 40-Apps/
│   └── <App>.md
├── 50-Knowledge/
│   ├── Domain-Topics.md
│   └── Acronyms.md
├── 60-Episodes/
│   ├── 2026-05-21.md                # daily, narrative
│   └── triggers-2026-05-21.md       # trigger audit log
├── 90-Inbox/
│   └── <pending-fact>.md            # user-review queue
└── .yukiignore
```

The vault is the source of truth. Every file is a real markdown file with YAML frontmatter and free-form body. Wikilinks (`[[Other Note]]`) connect notes — Yuki resolves them by frontmatter `id` first, falling back to filename.

### 4.2 Note Schema

Every note declares a `type` discriminator. Schemas (Pydantic, validated on read):

```yaml
# common to all notes
id: <slug>             # stable identifier, never changes
type: <type>           # person | project | routine | app | preference | episode | identity | knowledge | trigger
created_at: <iso>
updated_at: <iso>
confidence: <0..1>     # how sure Yuki is about this note overall
source: [<source>...]  # which collectors / observations contributed
```

Type-specific fields:

```yaml
type: person
name: str
role: str | null
relationship: "manager" | "report" | "peer" | "external" | "personal" | null
contact: { slack: str?, email: str?, phone: str? }
last_seen: <iso>
interaction_frequency: "daily" | "weekly" | "monthly" | "rare"

type: project
name: str
status: "active" | "paused" | "archived"
tech: [str...]
path: str?              # local repo path if applicable
last_touched: <iso>

type: routine
name: str
schedule: <cron-like or human description>
steps: [<wikilink>...]  # ordered references to other notes
trusted: bool           # whether routine can run without per-step confirm

type: app
name: str
bundle_id: str
importance: "primary" | "occasional" | "background"
common_uses: [str...]

type: trigger
enabled: bool
condition: { kind: ..., ... }
debounce: <duration>
action: { kind: "routine" | "tool_call" | "suggestion", ... }
last_fired: <iso>
fire_count: int
acceptance_rate: float
```

### 4.3 SQLite Index

`~/Library/Application Support/Yuki/index.db`:

```sql
CREATE TABLE notes (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT,
    body_hash TEXT,
    updated_at TEXT,
    confidence REAL,
    metadata JSON
);

CREATE TABLE links (
    src_id TEXT,
    dst_id TEXT,
    PRIMARY KEY (src_id, dst_id)
);

CREATE VIRTUAL TABLE note_vec USING vec0(
    embedding FLOAT[1536]
);

CREATE VIRTUAL TABLE note_fts USING fts5(id, title, body);

CREATE TABLE events (
    ts INTEGER NOT NULL,
    kind TEXT NOT NULL,
    payload JSON
);
CREATE INDEX events_ts ON events(ts);
```

Embeddings via Voyage AI or OpenAI `text-embedding-3-small` (one cheap call per note). Index is rebuildable from the markdown — losing the DB never loses memory.

### 4.4 Retrieval Tools

Three memory tools available to the agent:

| Tool | Behavior |
|---|---|
| `memory_search(query, k=5, types?)` | Hybrid: BM25 over `note_fts` + cosine over `note_vec`, RRF-merged. Returns top-k notes with frontmatter + 200-char snippet. |
| `memory_read(id_or_path, expand_links=1)` | Reads one note, optionally inlines linked notes one hop deep. |
| `memory_write(note_id, patch, confidence)` | Appends/updates a fact. If `confidence < 0.7`, queues to `90-Inbox/` instead of writing directly. |

Hot context (always-loaded, prompt-cached): `00-Identity/*.md` (~1–2KB) is injected into the system prompt every call so the model doesn't have to search for basics like the user's name.

---

## 5. Onboarding Scanner

Runs once on first launch. Builds the seed vault.

### 5.1 Permissions Wizard

SwiftUI sheet that walks each permission, opens System Settings if needed:

| Permission | Required? | Unlocks |
|---|---|---|
| Accessibility | Yes | All UI control |
| Screen Recording | Yes | Vision fallback |
| Calendars | No | EventKit-based scan + calendar tool + calendar triggers |
| Reminders | No | Reminders tool |
| Contacts | No | Person resolution in scan |
| Full Disk Access | No | Mail/Messages SQLite reads → richer scan |
| Microphone | No | Voice/wakeword |

Skipping any optional permission gracefully degrades; user is told once what each unlocks.

### 5.2 Scan Pipeline

Four stages, each a separate Python module:

```
┌─────────────┐    ┌────────────┐    ┌───────────────┐    ┌─────────────┐
│ Collectors  │ -> │ Normalizer │ -> │ Pattern det.  │ -> │ Note writer │
│ (parallel)  │    │            │    │               │    │             │
└─────────────┘    └────────────┘    └───────────────┘    └─────────────┘
   raw JSON          Fact tuples       Entity bundles      markdown notes
   ~30-60s           ~5s               ~1s                 ~10-20s
```

**Stage 1 — Collectors** (`scan/collectors/*.py`):

| Collector | Source |
|---|---|
| `system` | `system_profiler`, `defaults read`, `sw_vers` |
| `apps` | `/Applications`, `~/Applications`, Homebrew, MAS, LaunchServices |
| `screen_time` | `~/Library/Application Support/Knowledge/knowledgeC.db` (if accessible) |
| `calendar` | EventKit, last 90 days |
| `contacts` | `~/Library/Application Support/AddressBook/` SQLite |
| `mail` | Mail.app `Envelope Index` SQLite — sender frequency only, no body content |
| `files` | `mdfind 'kMDItemLastUsedDate >= $time.now(-90d)'` grouped by directory |
| `git` | walk `~/code` etc., `git log` per repo |
| `browser` | Safari/Chrome history SQLite — top domains by visit count |
| `shell` | `~/.zsh_history` / `~/.bash_history` — command frequency |

Output to `~/Library/Caches/Yuki/scan/raw/<collector>.json`.

**Stage 2 — Normalizer** (`scan/normalizer.py`):

```python
@dataclass
class Fact:
    subject: str          # "Sarah Chen" | "Slack" | "user"
    predicate: str        # "meets_with_recurring", "uses_app", "works_on_project"
    object: str
    confidence: float
    sources: list[str]
    evidence: list[dict]
    first_seen: datetime
    last_seen: datetime
```

Merges duplicate facts, resolves aliases (email → contact name, etc.).

**Stage 3 — Pattern Detector** (`scan/patterns.py`): hand-written rules cluster facts into typed entities. Examples:

```python
if subject_appears_in([calendar, mail, messages]) and contact_book.has(subject):
    entity_type = "person"
    importance = log(total_interactions)

if directory_modified_count > 20 and has_git_history:
    entity_type = "project"

if event_recurs_weekly and time_of_day < 11:
    entity_type = "routine"
    routine_kind = "morning"

if app_foreground_minutes_per_week > 30:
    entity_type = "app"
    importance = "primary"
```

**Stage 4 — Note Writer** (`scan/notewriter.py`):

- **Default path:** Jinja templates per entity type, deterministic. ~70% of notes go this way. Fast, free, offline.
- **LLM polish path (opt-in):** for entities with rich-but-ambiguous facts, batch-call Claude Haiku to write narrative summary. ~50¢ in tokens for full vault. User opts in on the consent screen.

### 5.3 Review UI

SwiftUI sheet shows everything Yuki learned, grouped by section. Items above 0.8 confidence pre-checked, below unchecked. Clicking any row shows the underlying source ("Source: 12 calendar events Jan–Mar 2026"). User clicks "Save vault" → notes written.

### 5.4 Indexer

After write, `memory/indexer.py` walks the vault, embeds each note, stores in SQLite. ~30s in background. User can use Yuki immediately; retrieval just gets sharper as embeddings finish.

---

## 6. Passive Observation & Episodes

After Day 1 the scanner is done. The observer daemon takes over to keep the vault fresh.

### 6.1 Event Sources (`observer/sources/*.py`)

All run as asyncio tasks subscribing to native callbacks. None poll. Total event rate on a normal day: 2,000–10,000 events.

| Source | API | Event |
|---|---|---|
| `workspace` | `NSWorkspace.didActivateApplicationNotification` | `app_focus` |
| `window` | AX `kAXFocusedWindowChanged` | `window_focus`, `window_title` |
| `browser` | AppleScript poll on browser focus only | `url_change` |
| `idle` | `CGEventSourceSecondsSinceLastEventType` (1s tick) | `idle_start`, `idle_end` |
| `calendar` | EventKit observer | `event_starting`, `event_ended` |
| `filesystem` | FSEvents on watched dirs | `file_modified` |
| `power` | IOKit notifications | `lock`, `unlock`, `sleep`, `wake`, `power_source_changed` |
| `network` | CWInterface | `wifi_changed` |

### 6.2 Ring Buffer + SQLite

`observer/ringbuffer.py` keeps the last 24h in memory; `observer/persistence.py` flushes to SQLite `events` table every 60s. Records ~30 days, configurable. 24h ≈ 2-5 MB.

### 6.3 Daily Episode

`episodist/builder.py` runs at 3am (or first wake after 3am). Reads yesterday's events, segments into sessions (gap >5 min = new session), labels each session via heuristics, writes one markdown file:

```markdown
~/YukiVault/60-Episodes/2026-05-21.md
```

User sees a daily review nudge in the menu-bar the next morning. They can read, edit, or redact before compaction.

### 6.4 Weekly Compaction

`episodist/compactor.py` runs Sunday morning, triggered by the `com.yuki.scheduler.plist` LaunchAgent (so it runs even if the menu-bar app was quit). Reads last 7-30 episodes. Calls Claude Haiku with the structured event log + tight prompt: "Identify recurring patterns. Output a JSON diff against the existing routine and people notes." Diffs:

- High-confidence (>0.85) → applied directly
- Lower-confidence → written to `90-Inbox/`, surfaced in next morning's review

This is how routines get written, refined, and updated. The compactor never makes raw observations into hard facts without crossing this threshold.

---

## 7. Tool Surface

### 7.1 Tier 1 — Inherited from MacOS-Use (UI primitives)

`click`, `type`, `scroll`, `move`, `shortcut`, `app` (launch/switch/resize), `shell` (bash/osascript), `scrape`, `desktop` (Spaces), `wait`, `done`. These are the backstop when no native tool covers a task.

### 7.2 Tier 2 — Native macOS tools (v1, full set)

| Tool | API | Danger | Notes |
|---|---|---|---|
| `calendar` | EventKit | external for create/invite, read_only otherwise | |
| `reminders` | EventKit | reversible | |
| `mail` | AppleScript + Mail SQLite | external for send (always confirms) | Body content via AppleScript. Send always confirms with full payload preview. |
| `notes` | AppleScript | reversible | |
| `messages` | AppleScript | external | **Behind feature flag** — re-evaluate at RC1. AppleScript surface is flaky. |
| `contacts` | Contacts.framework | read_only | |
| `files` | NSFileManager + `mdfind` | reversible / destructive (delete) | Delete = destructive, requires typed "yes". |
| `shortcuts` | `shortcuts` CLI | reversible (varies) | Runs user's existing Shortcuts. |
| `system` | IOKit / `defaults` | reversible | Volume, brightness, wifi, bluetooth, DND, dark mode. |
| `clipboard` | Pasteboard | reversible | Read/write + 20-item history. |
| `screenshot` | Quartz + Vision OCR | read_only | |
| `web_search` | User's Brave/Kagi/Google API key | read_only | Fallback: open browser. |
| `browser` | AppleScript + AX | reversible | Tab control, current page text. |
| `music` | MediaRemote | reversible | |
| `meeting` | Window detection + AX | external | **Behind feature flag** — Zoom/Meet/Teams AX surfaces shift. |

### 7.3 Tier 3 — Memory tools

`memory_search`, `memory_read`, `memory_write` (see §4.4).

### 7.4 Selection Heuristic

Baked into the system prompt:

> When a task can be accomplished via a native tool (calendar, reminders, mail, notes, etc.), prefer it over UI automation. Only fall back to click/type tools when no native tool covers the action, or when the user explicitly wants you to use the UI.

### 7.5 Danger Levels & Confirmation

```
read_only   → no confirmation
reversible  → one-tap confirm; auto-approvable inside trusted routine
external    → always confirm; full payload preview shown
destructive → typed-yes confirm; never auto-approvable
```

Two escape valves on top of "always confirm":
1. **Trusted routines** — after 5 identical successful executions of the same routine, Yuki offers to mark it trusted. Trusted routine = whole-routine confirm at start, then each `reversible` step runs without per-step confirm. `external`/`destructive` always confirm even inside trusted routines.
2. **Burst mode** — long-press `⌘⇧Y` → "I'm watching, just go" disables confirmation for `reversible` for 30 seconds.

### 7.6 Extensibility

User-extensible `@tool` decorator is **part of v1**. Users drop a Python file into `~/.yuki/tools/` containing one or more `@tool(name=, danger=)` functions; Yuki hot-reloads on file change. Tools live in a sandboxed import (their failure cannot crash the agent loop) and their danger level is the same `read_only/reversible/external/destructive` enum as built-ins, so the gatekeeper handles them uniformly. This decision was upgraded after observing that Raycast Extensions are the central reason power users adopt Raycast — the plugin surface IS the moat, not a polish item.

---

## 8. Trigger Engine

### 8.1 Trigger Definition

Triggers live as markdown files in `~/YukiVault/30-Routines/triggers/`. Frontmatter is the executable contract; body is human description. See §4.2 for `type: trigger` schema.

### 8.2 Categories (v1)

| Kind | Source | Example |
|---|---|---|
| `time` | `launchd` calendar interval | "0 9 * * 1-5" → morning routine suggestion |
| `calendar` | EventKit observer | 5 min before event → "join Zoom?" |
| `app_state` | NSWorkspace activation | "user opened Linear" → "filter to your sprint?" |
| `idle` | observer idle events | "idle 45 min after 6pm" → "wrap up day?" |
| `deviation` | live pattern match | "10:02 Tuesday but standup not started" |
| `external` | network / power / location | "joined home wifi after 7pm" → evening profile |

### 8.3 Engine Loop

`triggers/engine.py` is a single asyncio loop subscribing to the observer event stream. For each event, walks enabled triggers, calls `trig.matches(event)`, fires presenter if match + not in debounce.

### 8.4 Presenter

Three surfaces by urgency:

| Urgency | Surface | Sound |
|---|---|---|
| Low | Menu-bar badge | none |
| Medium | macOS notification | soft |
| High | Modal in chat overlay | none |

Suggestion shape (uniform):

```
[ Yuki suggestion ]
<one-line description of the proposed action>
   [ Yes ]   [ Modify ]   [ Not now ]   [ Never again ]
```

### 8.5 Self-Pruning

Each trigger tracks `fire_count`, `acceptance_rate`. If `acceptance_rate < 0.3` after 10 fires, Yuki proposes disabling it.

### 8.6 Deviation Alerts (v1, conservative)

Only 4-5 specific kinds enabled at v1:

- `missed_recurring_meeting` — recurring calendar event but no Zoom/Meet/Teams app open at start time
- `project_cadence_drop` — usual project hasn't been touched in N× normal interval
- `end_of_day_overrun` — work apps still focused well past usual quit time
- `app_time_overrun` — single app way over its usual daily duration
- `routine_partial_match` — opened first 2 of 3 routine apps, didn't open the third

Each user-toggleable in Settings.

### 8.7 Mute UX

Two layers:
- Menu-bar quick mute: "1h / today / weekend / until tomorrow 9am"
- Settings: per-category kill switches ("never calendar triggers", "never deviation alerts")

Observer keeps running while triggers muted — memory stays fresh.

### 8.8 Audit

Every fired suggestion logged to `~/YukiVault/60-Episodes/triggers-YYYY-MM-DD.md` with full context.

---

## 9. Invocation Surfaces

### 9.1 Global Hotkey

Default `⌘⇧Y`. Opens chat overlay (lightweight SwiftUI window, not full frontend). Configurable in Settings.

### 9.2 Wakeword (opt-in, off by default)

"Hey Yuki" detection via Whisper streaming + small wakeword model. Requires Microphone permission. User toggles in Settings.

### 9.3 Menu-bar Click

Click icon → popover with quick chat input, last conversation preview, mute toggle, "Open full chat" link.

### 9.4 Full Frontend (Next.js)

Opens in default browser at `http://127.0.0.1:<random-port>?token=<launch-token>`. Chat history, settings, memory browser, trigger manager, scheduled tasks. Ported from Yuki/LLM-OS.

---

## 10. Packaging & Distribution

### 10.1 Bundle

```
Yuki.app  (~120-180 MB, signed + notarized)
├── Contents/MacOS/Yuki                    # Swift menu-bar binary
├── Contents/Resources/frontend/           # Next.js static export
├── Contents/Resources/icons/
└── Contents/Frameworks/Python.framework/  # python-build-standalone + venv
```

### 10.2 Build Pipeline (Briefcase)

GitHub Actions on tag push:

```
1. Cache Python deps
2. Build frontend (next build, static export)
3. Briefcase build for arm64 + x86_64
4. Sign with Developer ID Application cert
5. Notarize via xcrun notarytool
6. Staple ticket
7. Build + sign .dmg
8. Upload to GitHub Releases
9. Update appcast.xml for Sparkle
10. Update Homebrew Cask formula
```

End-to-end: ~20 min per release.

### 10.3 Auto-Update

Sparkle. `appcast.xml` hosted on our domain. Update check on launch + once daily. Update applied on next quit.

### 10.4 First-Run Experience

```
1. Mount Yuki-1.0.0.dmg
2. Drag Yuki.app → Applications
3. Double-click → Gatekeeper passes
4. 3-slide welcome
5. Permissions wizard
6. API key entry (Anthropic / OpenAI / Google) → validated → Keychain
7. Onboarding scan (~60-90s, progress UI)
8. Review UI (user-paced)
9. Vault writes to ~/YukiVault/
10. Indexer embeds notes (~30s, background)
11. Trigger discovery — user enables 0-N proposed triggers
12. Done screen with cheatsheet
13. Menu-bar icon live
```

Total: ~8-12 min including human-paced steps.

### 10.5 Uninstall

Settings → "Uninstall Yuki" performs:
1. Stop both LaunchAgents
2. Remove plists
3. Remove Keychain entries
4. Ask: "Keep your vault at `~/YukiVault/`?" (default yes)
5. Remove `~/Library/Application Support/Yuki/`
6. Remove `~/Library/Caches/Yuki/`
7. Quit; user drags Yuki.app to Trash

### 10.6 Distribution

- **v1**: GitHub Releases + Homebrew Cask (`brew install --cask yuki`)
- **v2+**: Mac App Store explicitly rejected — sandbox would gut several tools

### 10.7 Telemetry

Zero. No analytics, no crash reports, no usage events leave the machine. "Export diagnostics" button in Settings produces a sanitized zip the user can attach manually to GitHub issues.

---

## 11. Security & Safety

### 11.1 Local-Only

- Backend bound to `127.0.0.1` only, never to `0.0.0.0`
- Per-launch random auth token; frontend gets it via URL
- Vault files have user-only permissions (`0600` for files, `0700` for dir)
- API keys in macOS Keychain, never in files

### 11.2 LLM Privacy

- Vault is never sent wholesale to the LLM
- Each call sends: system prompt + identity hot-context (~2KB) + retrieved snippets for the current query (~5-15KB) + active window state
- Anthropic prompt caching reduces repeat-token cost
- User can review exactly what was sent in the chat history (full transcript visible per turn)

### 11.3 Action Safety

Confirmation policy + tool danger levels (§7.5). Audit log of every executed action in episodes.

### 11.4 No Network Without Reason

Outbound connections only to:
- The user's chosen LLM provider
- Embedding API (Voyage / OpenAI)
- Sparkle update server (our domain)
- Web search if user enables `web_search_tool`
- Auto-update server

No analytics, no error tracking, no anonymous pings.

---

## 12. Out of Scope for v1

Explicit non-goals to keep v1 shippable:

- **OCR-based screen content capture** — opt-in path designed but not shipped at v1
- **Per-app deep integrations beyond AppleScript** — Slack/Linear/Notion APIs deferred
- **Voice content recording / meeting transcription** — even with permission, cuts too much surface
- **iOS/iPad sync** — vault is Mac-only at v1; could extend via iCloud Drive in v1.x
- **Multi-user / family** — single-user only
- **Cross-platform** — macOS 12+ only; Windows users use original Yuki
- **Encrypted vault** — vault is plaintext; users wanting encryption should put `~/YukiVault/` on an encrypted volume (FileVault covers this for the OS already)
- **Cross-process tool sandboxing** — v1 hot-reloads user tools in-process; OS-level sandboxing per tool is a v1.1 concern
- **Fine-tuning on user data** — never; we use prompt caching + retrieval, not training

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| MacOS-Use upstream stalls or diverges | We've forked. We can keep cherry-picking or stop tracking — fork is MIT, fully ours. |
| Apple deprecates AppleScript / TCC tightens | Each tool has a fallback (click/type). System prompt rule prefers native, but degrades. |
| Wakeword model is mediocre on Mac mics | Off by default. Hotkey is the real entry point. |
| Onboarding scan privacy panic | Permissions wizard is granular; review UI shows everything before save; "uninstall keeps vault" gives control. |
| LLM cost spikes for active users | Prompt caching + Haiku for compaction + only retrieved snippets sent. Budget warning in Settings if month-to-date estimate crosses threshold. |
| Trigger spam annoying users | Self-pruning; mute presets; per-type kill switches; conservative deviation v1. |
| Code signing / notarization breaks CI | Standard Apple developer workflow with established tooling (Briefcase handles most of it). |
| Messages and Meeting tools are flaky | Both behind feature flag — cut from v1 if not stable at RC1. |
| Vault corruption | SQLite index is rebuildable. Markdown files are plain text. Daily backup of vault to `~/Library/Application Support/Yuki/backups/` (rolling 7 days). |

---

## 14. Open Questions for Implementation Plan

These are settled at design level but need detail in the implementation plan:

1. **Embedding provider default** — Voyage vs. OpenAI `text-embedding-3-small`? Cost vs. quality vs. extra key.
2. **Vault file naming** — slugified human name vs. opaque id-based filenames? Affects readability vs. rename safety.
3. **Trusted-routine activation count** — 5 successes is a guess; may need user research.
4. **Compaction LLM cost ceiling** — hard cap per week to prevent surprise bills.
5. **Migration path when MacOS-Use upstream changes** — automated cherry-pick vs. manual review.
6. **Frontend port** — Yuki/LLM-OS frontend → our backend likely needs ~2 weeks of porting work; quantify.
7. **Test strategy** — AX-driven UI is hard to test; what's our minimum viable test surface?

---

## 15. Acceptance Criteria for v1

Yuki ships when:

1. User can install via signed `.dmg` or `brew install --cask yuki`
2. First-run takes ≤10 minutes from .dmg to working assistant
3. Onboarding scan produces ≥50 vault notes for a typical 6-month-old Mac
4. All 15 native tools (with messages + meeting behind feature flag, cuttable to 13 if flaky) work under happy-path scripted tests
5. Memory retrieval surfaces relevant notes for ≥80% of "who/what is X" queries about scanned entities
6. Triggers fire correctly for time + calendar + app-state categories under integration tests
7. "Always ask" confirmation works for all `external` and `destructive` tools
8. Trusted routines activate after 5 successes and respect the danger-level rules
9. Daily episode is written every morning and visible in vault
10. Weekly compactor produces a vault diff that the user can review
11. Uninstall leaves no LaunchAgents, Keychain entries, or Application Support files
12. Zero network calls observed in tcpdump beyond the documented allowed list
13. App size ≤200MB
14. Cold start to chat-ready ≤3 seconds on Apple Silicon, ≤5 seconds on Intel
