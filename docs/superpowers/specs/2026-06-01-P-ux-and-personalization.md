# Plan P: Command-bar UX + Personalization (Round 1) — Design Spec

**Status:** Approved design — ready for implementation planning.
**Date:** 2026-06-01

**Goal:** Make the command bar feel like a real chat app, and turn the dormant
personalization system into something the user can see, seed, and steer.

**Architecture:** The Swift command bar flips to a chat-style layout (conversation
on top, input pinned at bottom) and becomes the single source of truth for task
activity and results — control tasks stream into the conversation instead of
escaping to the corner HUD. On the Python side, a thin "memory store" exposes the
already-existing vault sections as editable facts over a REST API, the dormant
daily learner gets switched on via a managed LaunchAgent, and chat replies can
carry an optional capture suggestion for inline "remember this?" prompts.

**Tech stack:** SwiftUI/AppKit (NSPanel, @FocusState, NSHostingView), FastAPI over
UDS, the existing `Vault`/`load_hot_context`/`recorder`/`learner` modules,
`launchctl`-managed LaunchAgent, bundled python-build-standalone interpreter.

---

## Context: what already exists (do not rebuild)

Verified by exploration on 2026-06-01:

- **Episode recording works.** After each `/control` task, `recorder.append_task_record`
  writes structured YAML to `~/YukiVault/60-Episodes/control-YYYY-MM-DD.md`.
- **Identity injection works.** `load_hot_context` reads `00-Identity` notes into
  every chat/control system prompt (`chat.py:72`, `chat.py:156`).
- **The vault exists on disk** with all sections (`00-Identity`, `10-People`,
  `20-Projects`, `40-Apps`, `60-Episodes`, …) under `~/YukiVault/`.
- **App-notes learning works** (one example: `40-Apps/WhatsApp.md`).

What is **broken / missing** (the reason personalization feels absent):

1. The **daily learner never runs** — `yuki/feedback/learner.py` + `cli.py` exist,
   but no LaunchAgent is installed (`~/Library/LaunchAgents/com.yuki.*` absent).
   Episodes accumulate; nothing is distilled.
2. The **Identity/People/Projects folders are empty** — injection works but has
   nothing to inject, and there is no UI to fill them.
3. **No control surface** — nothing in the app shows, edits, or steers what Yuki
   knows.

The command bar also has five UX defects (root causes in `CommandBar.swift`):

| Defect | Root cause |
|---|---|
| Clicking outside doesn't dismiss | `KeyablePanel` only handles Esc (`cancelOperation`) |
| Loader shows above the "yuki" header | `ProgressView` rendered in header zone, above the divider |
| Final response missing after a task | `route()` calls `CommandBar.shared.close()` + `enqueueControl` → HUD, which fades after 5s; result never returns to the thread |
| Must click input after every response | `inputFocused` only re-asserted on toggle, not after a turn completes |
| Conversation "doesn't show up perfectly" | inverted input-on-top layout fights newest-at-bottom streaming |

---

## Part 1 — Command bar redesign (chat-style)

### 1.1 Layout flip

`CommandBarView` changes from input-on-top to **conversation-on-top, input-pinned-
bottom**:

- Conversation `ScrollView` fills the available height, newest turn at the bottom,
  auto-scrolls on new content (existing `ScrollViewReader` logic is reused).
- The input `TextField` is pinned to the bottom in its own bar (visually distinct
  background, e.g. `.regularMaterial` strip), always visible.
- The context badge (`ctxBadge`) moves to the bottom bar's trailing edge (small,
  tertiary), removing the separate header row.
- Panel size stays 720×420.

### 1.2 Click-outside dismissal

`KeyablePanel` keeps Esc-to-close. Add click-outside dismissal: install a
global/local `NSEvent` monitor for `leftMouseDown`/`rightMouseDown` while the panel
is visible; if the click falls outside the panel frame, `orderOut(nil)`. Remove the
monitor when the panel hides. (Alternative acceptable implementation: override
`resignKey` to order out — but a global monitor is more reliable for an accessory
app whose key status is shared with apps the agent drives. Implementer picks; the
behavior is: click anywhere outside → bar closes.)

### 1.3 Loader becomes an inline activity bubble

Delete the header `ProgressView`. While a turn is in flight, append a **single
transient activity line** to the conversation:

- Plain chat: `Thinking…`
- Control task: `Working on it — <verb>…`, where `<verb>` is derived from the live
  tool-call stream using the existing verb map (`HUD.verbMap`: app_tool→"Switching
  to", click_tool→"Clicking", type_tool→"Typing", etc.). The line **updates in
  place** as tool calls arrive.

On completion, the transient line is **removed** and replaced by the final result
turn (✓ success text, or ✗ error text). This is option A from the activity-stream
mockup: one live line, collapses to result. Full step detail remains live in the
corner HUD and permanently in the Episodes vault.

**Implementation note:** the transient line is modeled as a distinct, non-persisted
item (e.g. a `@State var liveActivity: String?` rendered below `history`, not a
`Turn` in `history`), so replacing it with the final result is a simple state swap
and it never pollutes the persisted conversation.

### 1.4 Control tasks stream into the conversation (core fix)

Today `route()` does:

```swift
if decision == "control" {
    CommandBar.shared.close()
    Backend.shared.enqueueControl(msg)   // → HUD only, fades in 5s
}
```

New behavior:

- The bar **stays open**.
- It subscribes to the control task's SSE event stream via a new
  `Backend.runControlInBar(_:onEvent:)` that forwards every event to a closure the
  bar owns (the existing `/chat/control` stream is already event-rich — `tool_call`,
  `done`, `error`).
- On `tool_call` events, the bar updates `liveActivity` (§1.3).
- On `done`, the bar appends the final content as an `ai` `Turn` and clears
  `liveActivity`.
- On `error`, the bar appends the error as an `ai` `Turn` (styled as failure) and
  clears `liveActivity`.
- The corner **HUD stays** for glanceable status when the bar is closed (e.g. the
  user dismissed it to watch the agent drive another app), but the **conversation
  is the source of truth** — reopening the bar shows the full history including the
  task result. The existing `enqueueControl`/HUD path remains for the bar-closed
  case; the new in-bar path is used when the bar is open at submit time.

**FIFO note:** the existing `controlTail` serialization (one desktop task at a time)
must be preserved so two tasks never fight the mouse. The in-bar path participates
in the same serialization.

### 1.5 Persistent focus

After any turn completes and `busy` flips to `false`, re-assert `inputFocused =
true` (post the existing `CommandBar.focusRequest` notification, or set the
`@FocusState` directly on the main actor). Result: the input is focused on open and
stays focused after every response — no repeated clicking.

---

## Part 2 — Personalization & Memory (foundation-first)

### 2.1 Memory store (Python)

New module `yuki/memory/store.py`: a fact-oriented view over the existing `Vault`.

- A **fact** = one markdown note in a personalization section. Sections in scope:
  `00-Identity`, `10-People`, `20-Projects`, `40-Apps`.
- `list_facts() -> list[Fact]` where `Fact = {id, section, title, text}` — `id` is
  the note's stable id/filename; iterate via the existing `Vault.list_section`.
- `add_fact(section, text) -> Fact` — creates a note (frontmatter + body) in the
  section using the existing vault note-writing path; title derived from the first
  line / a short slug.
- `delete_fact(id)` — removes the note file (and de-indexes if the indexer tracks it).
- Section routing for `/remember` and capture: default to `00-Identity`; if the text
  clearly names a person → `10-People`, a project → `20-Projects` (simple keyword/
  heuristic; the implementer keeps it deterministic, no LLM).

### 2.2 Memory API (Python)

New router `yuki/backend/routers/memory.py`, registered in `server.py`:

- `GET /memory` → `{sections: {identity: [Fact], people: [...], projects: [...], apps: [...]}}`
- `POST /memory` `{section, text}` → created `Fact`
- `DELETE /memory/{id}` → `{ok: true}`
- `GET /settings/memory` → `{learner_enabled: bool, ask_before_remember: bool}`
- `POST /settings/memory` `{learner_enabled?, ask_before_remember?}` → persists to
  `app_state.json` and returns the new state.

`appstate.py` gains defaults: `learner_enabled: true`, `ask_before_remember: true`.

### 2.3 Daily learner — turn it on

New `LaunchAgentManager.swift` (app side):

- Writes/loads `~/Library/LaunchAgents/com.yuki.feedback.learner.plist` that runs the
  **bundled** interpreter: `…/Resources/python/bin/python3 -m yuki.feedback.cli`
  with `PYTHONPATH` set to the bundled site-packages (same env the backend uses in
  `BackendController.swift`), on a daily `StartCalendarInterval` (e.g. 03:00).
- `enable()` → write plist + `launchctl load`; `disable()` → `launchctl unload` +
  remove plist.
- Driven by the "Daily learning" toggle (§2.4). On app launch, reconcile: if the
  toggle is on and the plist is missing/stale, (re)install it.

`feedback/cli.py` must run clean under the bundled interpreter (verify imports
resolve against bundled site-packages; it already routes the learner through
`make_llm`).

The cask `zap` already lists `com.yuki.feedback.learner.plist` — uninstall covered.
`release.sh` ships a plist **template** (or the app generates it at runtime with the
correct bundle paths — runtime generation is preferred since paths are
install-location-dependent).

### 2.4 Settings → Memory tab (Swift)

New tab in the existing `Settings.swift` TabView, between Permissions and About:

- **Facts lists**, grouped by section (Identity / Projects / People / App-notes):
  each fact shown as an editable/removable row; a delete (`–`) per row.
- **"Add a fact"** field + section picker → `POST /memory`.
- **Toggles:**
  - *Daily learning* (on/off) → `POST /settings/memory` + `LaunchAgentManager`
    enable/disable.
  - *Ask before remembering* (on/off) → `POST /settings/memory`.
- Loads via `GET /memory` + `GET /settings/memory` on appear.

`Backend.swift` gains: `memory()`, `addFact(section:text:)`, `forgetFact(id:)`,
`memorySettings()`, `setMemorySettings(...)`.

### 2.5 Slash commands in the bar (Swift)

Extend `submit()` dispatch (joins existing `/clear`, `/compact`):

- `/memory` → calls `Backend.memory()`, renders grouped facts as an `ai` `Turn`.
- `/remember <fact>` → `Backend.addFact` (section auto-routed server-side), appends
  a confirmation `ai` `Turn` ("Got it — I'll remember that.").
- `/forget` → renders the numbered fact list; a follow-up `/forget <n>` removes that
  fact via `Backend.forgetFact`. (Implementer may choose an inline list-with-delete
  affordance instead; behavior: user can remove a specific fact from the bar.)

### 2.6 Conversational capture ("remember this?")

- `chat.py` `/chat` reply gains an optional field `capture_suggestion: {text} | null`.
  The chat system prompt instructs the model to, **alongside its normal reply**,
  emit a `capture_suggestion` when the user states a durable personal fact (e.g.
  "I always use Linear for tickets"). No second LLM round-trip — it rides along in
  the same completion. (Decision: "LLM flags it in the same reply.")
- Gated by `ask_before_remember`. When present and the toggle is on, the bar renders
  an inline **"Remember this? [Yes] [No]"** affordance under the reply. **Yes** →
  `POST /memory` (section auto-routed). **No** → dismiss.
- Only applies to **plain chat** turns, not control tasks.

---

## Part 3 — Files & components

**Swift (`app/Yuki/`):**
- `CommandBar.swift` — bottom-input layout; click-outside dismissal; inline activity
  bubble; in-bar control streaming; persistent focus; slash commands; "remember
  this?" affordance.
- `Backend.swift` — `runControlInBar(_:onEvent:)`, `memory()`, `addFact()`,
  `forgetFact()`, `memorySettings()`, `setMemorySettings()`.
- `Settings.swift` — new Memory tab.
- `LaunchAgentManager.swift` (new) — learner plist load/unload, launch-time reconcile.

**Python (`yuki/`):**
- `memory/store.py` (new) — fact view over `Vault`.
- `backend/routers/memory.py` (new) — memory CRUD + memory settings.
- `backend/server.py` — register the memory router.
- `backend/routers/chat.py` — emit `capture_suggestion`; ensure control stream is
  consumable in-bar (already streams).
- `backend/appstate.py` — `learner_enabled`, `ask_before_remember` defaults.
- `feedback/cli.py` — verify clean run under bundled interpreter.

**Packaging:**
- App generates the learner plist at runtime with correct bundled paths (preferred
  over a static template, since paths depend on install location). Cask `zap`
  already lists the plist.

---

## Part 4 — Testing

- **Python (real unit tests):** `memory/store.py` CRUD (add/list/delete across the 4
  sections, section routing heuristic); `/memory` + `/settings/memory` endpoints
  (happy path + bad section + missing id); `capture_suggestion` shape in `/chat`
  reply; `appstate` toggle defaults + persistence.
- **Swift (manual QA):** UI behavior verified on the live app — layout, click-outside,
  inline loader, in-bar task results, persistent focus, Memory tab, slash commands,
  "remember this?" affordance, learner toggle actually loads/unloads the LaunchAgent.
  Consistent with the project's established "implement; user tests the live app"
  workflow.

---

## Out of scope (deferred to later specs)

- **Mac-observation** (passive app/window-usage sampling to infer routines) — its own
  spec; bigger build, new always-on process, additional privacy surface.
- Notarization (separate, known follow-up).
- Expandable step-log in the conversation (option B from the activity mockup) — can be
  added later if the single live line proves insufficient.

---

## Decisions locked during brainstorming

- Command-bar layout: **chat-style, input pinned at bottom** (B).
- Task activity in thread: **single live line, collapses to result** (A).
- Memory surface: **Settings tab + slash commands, both** (C), feeding one store.
- Learning scope this round: **foundation first** — learner on + Memory UI +
  conversational capture; Mac-observation deferred.
- Capture trigger: **LLM flags it in the same chat reply** (no extra round-trip).
- Commits follow the repo convention: **no Claude attribution / Co-Authored-By**.
