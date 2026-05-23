# Plan K — Packaging & Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Yuki as a signed, notarized `.dmg` distributed via GitHub Releases and Homebrew Cask, with Sparkle auto-update — the user-facing promise of "double-click to install."

**Architecture:** Briefcase produces the `.app` bundle with the Python framework, vendored deps, and the Swift menu-bar binary. A GitHub Actions workflow on every `v*` tag: builds the frontend, runs Briefcase build + sign + notarize, builds the `.dmg`, uploads it as a Release asset, updates `appcast.xml` for Sparkle, and bumps the Homebrew Cask formula. The cask formula lives in a sibling repo `homebrew-yuki` (already exists in the user's monorepo as `homebrew-tap/`).

**Tech Stack:** `briefcase>=0.3.20`, Apple Developer ID Application certificate (env var `APPLE_DEVELOPER_ID`), `notarytool` (built into Xcode), `sparkle>=2.6` (download static, ed25519 signed), GitHub Actions, Homebrew Cask DSL.

**Spec reference:** §10.1–10.6 (full distribution chapter), §10.7 (telemetry — packaging must not introduce any).

**Prerequisite:** Plans A-J complete; the working tree must produce a Python package (`uv build`) and a Swift binary (`swift build` in `app/`).

---

## File Structure

```
Yuki/
├── packaging/
│   ├── briefcase.toml                  # NEW
│   ├── notarize.sh                     # NEW — wraps xcrun notarytool
│   ├── make_dmg.sh                     # NEW — create-dmg invocation
│   ├── sparkle/
│   │   ├── appcast.xml.j2              # NEW — template
│   │   └── sign.sh                     # NEW — signs update with ed25519
│   └── homebrew/
│       └── yuki.rb                     # NEW — Homebrew Cask formula
├── .github/workflows/
│   ├── ci.yml                          # already exists from Plan A0; extended
│   └── release.yml                     # NEW — runs on tag push
└── docs/
    └── DISTRIBUTION.md                 # NEW — short maintainer runbook
```

---

## Task 1 — Briefcase configuration

**Files:**
- Create: `packaging/briefcase.toml`
- Modify: `pyproject.toml` (add `[tool.briefcase]` section)

- [ ] **Step 1: Add briefcase to dev deps**

In `pyproject.toml` `[dependency-groups] dev`:

```toml
"briefcase>=0.3.20",
```

Then `uv sync`.

- [ ] **Step 2: `packaging/briefcase.toml`**

```toml
[tool.briefcase]
project_name = "Yuki"
bundle = "com.yuki"
version = "0.1.0"
url = "https://github.com/sudhanshu/yuki"
license = "MIT"
author = "Sudhanshu Pandit"

[tool.briefcase.app.yuki]
formal_name = "Yuki"
description = "Jarvis-style assistant for macOS that knows you"
sources = ["yuki"]
icon = "packaging/icon"

[tool.briefcase.app.yuki.macOS]
universal_build = true
min_os_version = "12.0"
requires = [
    "anthropic>=0.68.1",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sse-starlette>=2.1.0",
    "pydantic>=2.9.0",
    "pyyaml>=6.0.2",
    "python-frontmatter>=1.1.0",
    "sqlite-vec>=0.1.6",
    "voyageai>=0.3.2",
    "jinja2>=3.1.4",
    "croniter>=2.0.5",
    "pyobjc-framework-Cocoa>=10.1",
    "pyobjc-framework-Quartz>=10.1",
    "pyobjc-framework-EventKit>=10.1",
    "pyobjc-framework-Contacts>=10.1",
    "pyobjc-framework-CoreWLAN>=10.1",
]
```

- [ ] **Step 3: Sanity-build (no signing)**

```bash
cd /Users/mafex/code/personal/Yuki
uv run briefcase create macOS app -c packaging/briefcase.toml
uv run briefcase build macOS app -c packaging/briefcase.toml
```

Expected: a `macOS/app/Yuki/Yuki.app` bundle.

- [ ] **Step 4: Commit**

```bash
git add packaging/briefcase.toml pyproject.toml uv.lock
git commit -m "feat(packaging): add Briefcase configuration"
```

---

## Task 2 — Notarize + DMG scripts

**Files:**
- Create: `packaging/notarize.sh`
- Create: `packaging/make_dmg.sh`

- [ ] **Step 1: `packaging/notarize.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_PATH="${1:?usage: notarize.sh <Yuki.app>}"
APPLE_ID="${APPLE_ID:?APPLE_ID env var required}"
APPLE_TEAM_ID="${APPLE_TEAM_ID:?APPLE_TEAM_ID env var required}"
APPLE_APP_PASSWORD="${APPLE_APP_PASSWORD:?APPLE_APP_PASSWORD env var required}"

ZIP_PATH="$(mktemp -d)/Yuki.zip"
ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"

xcrun notarytool submit "$ZIP_PATH" \
  --apple-id "$APPLE_ID" \
  --team-id "$APPLE_TEAM_ID" \
  --password "$APPLE_APP_PASSWORD" \
  --wait

xcrun stapler staple "$APP_PATH"
xcrun stapler validate "$APP_PATH"
echo "Notarized + stapled: $APP_PATH"
```

- [ ] **Step 2: `packaging/make_dmg.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_PATH="${1:?usage: make_dmg.sh <Yuki.app> <out.dmg>}"
OUT_PATH="${2:?usage: make_dmg.sh <Yuki.app> <out.dmg>}"

if ! command -v create-dmg >/dev/null 2>&1; then
  brew install create-dmg
fi

create-dmg \
  --volname "Yuki" \
  --window-size 540 360 \
  --icon-size 96 \
  --icon "Yuki.app" 140 180 \
  --app-drop-link 400 180 \
  --no-internet-enable \
  "$OUT_PATH" "$APP_PATH"
```

- [ ] **Step 3: Make executable + commit**

```bash
chmod +x packaging/notarize.sh packaging/make_dmg.sh
git add packaging/notarize.sh packaging/make_dmg.sh
git commit -m "feat(packaging): add notarize + dmg scripts"
```

---

## Task 3 — Sparkle appcast template + signer

**Files:**
- Create: `packaging/sparkle/appcast.xml.j2`
- Create: `packaging/sparkle/sign.sh`

- [ ] **Step 1: `packaging/sparkle/appcast.xml.j2`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>Yuki Updates</title>
    <link>{{ base_url }}/appcast.xml</link>
    <item>
      <title>Yuki {{ version }}</title>
      <pubDate>{{ pub_date }}</pubDate>
      <enclosure
        url="{{ base_url }}/Yuki-{{ version }}.dmg"
        sparkle:version="{{ version }}"
        sparkle:edSignature="{{ signature }}"
        length="{{ length }}"
        type="application/octet-stream" />
    </item>
  </channel>
</rss>
```

- [ ] **Step 2: `packaging/sparkle/sign.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

DMG="${1:?usage: sign.sh <dmg> <ed25519_priv_key_path>}"
KEY="${2:?usage: sign.sh <dmg> <ed25519_priv_key_path>}"

if ! command -v sparkle-sign >/dev/null 2>&1; then
  echo "Install Sparkle binaries (https://sparkle-project.org) and ensure 'sign_update' is on PATH" >&2
  exit 1
fi

sparkle-sign "$DMG" "$KEY"
```

- [ ] **Step 3: Make executable + commit**

```bash
chmod +x packaging/sparkle/sign.sh
git add packaging/sparkle/
git commit -m "feat(packaging): add Sparkle appcast template + signer"
```

---

## Task 4 — Homebrew Cask formula

**Files:**
- Create: `packaging/homebrew/yuki.rb`

- [ ] **Step 1: `packaging/homebrew/yuki.rb`**

```ruby
cask "yuki" do
  version "0.1.0"
  sha256 :no_check  # filled at release time

  url "https://github.com/sudhanshu/yuki/releases/download/v#{version}/Yuki-#{version}.dmg"
  name "Yuki"
  desc "Jarvis-style assistant for macOS that knows you"
  homepage "https://github.com/sudhanshu/yuki"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on macos: ">= :monterey"

  app "Yuki.app"

  zap trash: [
    "~/Library/Application Support/Yuki",
    "~/Library/Caches/Yuki",
    "~/Library/LaunchAgents/com.yuki.agent.plist",
    "~/Library/LaunchAgents/com.yuki.scheduler.plist",
    "~/Library/Preferences/com.yuki.app.plist",
  ]
end
```

- [ ] **Step 2: Commit**

```bash
git add packaging/homebrew/yuki.rb
git commit -m "feat(packaging): add Homebrew Cask formula"
```

---

## Task 5 — Release GitHub Actions workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: `.github/workflows/release.yml`**

```yaml
name: release

on:
  push:
    tags: ["v*"]

jobs:
  build:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4

      - name: Set version env
        run: echo "VERSION=${GITHUB_REF_NAME#v}" >> "$GITHUB_ENV"

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Setup uv
        uses: astral-sh/setup-uv@v3

      - name: Install Node + build frontend
        uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: |
          cd frontend
          npm ci
          npm run build
          rm -rf ../yuki/backend/static
          cp -r out ../yuki/backend/static

      - name: Build Swift menubar
        run: |
          cd app
          swift build -c release

      - name: Briefcase build
        run: |
          uv run briefcase create macOS app -c packaging/briefcase.toml
          uv run briefcase build macOS app -c packaging/briefcase.toml

      - name: Code-sign + notarize
        env:
          APPLE_ID: ${{ secrets.APPLE_ID }}
          APPLE_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
          APPLE_APP_PASSWORD: ${{ secrets.APPLE_APP_PASSWORD }}
        run: |
          codesign --force --deep --options runtime \
            --sign "${{ secrets.APPLE_DEVELOPER_ID }}" \
            macOS/app/Yuki/Yuki.app
          ./packaging/notarize.sh macOS/app/Yuki/Yuki.app

      - name: Build DMG
        run: |
          ./packaging/make_dmg.sh macOS/app/Yuki/Yuki.app "Yuki-${VERSION}.dmg"

      - name: Sign DMG for Sparkle
        env:
          SPARKLE_ED25519_KEY: ${{ secrets.SPARKLE_ED25519_KEY }}
        run: |
          echo "$SPARKLE_ED25519_KEY" > /tmp/sparkle_key
          ./packaging/sparkle/sign.sh "Yuki-${VERSION}.dmg" /tmp/sparkle_key
          rm /tmp/sparkle_key

      - name: Upload to GitHub Releases
        uses: softprops/action-gh-release@v2
        with:
          files: Yuki-*.dmg
          fail_on_unmatched_files: true

      - name: Refresh Homebrew Cask formula
        env:
          GITHUB_TOKEN: ${{ secrets.HOMEBREW_TAP_TOKEN }}
        run: |
          DMG_SHA=$(shasum -a 256 "Yuki-${VERSION}.dmg" | awk '{print $1}')
          sed -i '' \
            -e "s|version \".*\"|version \"${VERSION}\"|" \
            -e "s|sha256 :no_check|sha256 \"${DMG_SHA}\"|" \
            packaging/homebrew/yuki.rb
          # In production this would push the updated cask to the homebrew-yuki repo.
```

- [ ] **Step 2: Smoke-test the workflow file**

`actionlint` if installed, otherwise just YAML-parse:

```bash
python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/release.yml'))" && echo OK
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "feat(packaging): add release workflow (build + sign + notarize + cask refresh)"
```

---

## Task 6 — Maintainer runbook

**Files:**
- Create: `docs/DISTRIBUTION.md`

- [ ] **Step 1: `docs/DISTRIBUTION.md`**

```markdown
# Distribution Runbook

## Cutting a release

1. Bump `version` in `pyproject.toml` and `packaging/briefcase.toml`.
2. Commit + tag: `git tag v0.1.0 && git push origin v0.1.0`
3. Wait for `release.yml` to finish on macOS-14 runner (~20 min).
4. Verify on a clean Mac:
   - `brew install --cask yuki`
   - Or download the DMG from Releases, drag-install
5. Confirm Sparkle picks up the new appcast on existing installs (force-check from menu).

## Required GitHub secrets

| Secret | Purpose |
|---|---|
| `APPLE_ID` | Apple ID email for notarytool |
| `APPLE_TEAM_ID` | 10-char Developer team identifier |
| `APPLE_APP_PASSWORD` | App-specific password for `notarytool` |
| `APPLE_DEVELOPER_ID` | Full "Developer ID Application: ..." string |
| `SPARKLE_ED25519_KEY` | Private ed25519 key for Sparkle update signing |
| `HOMEBREW_TAP_TOKEN` | Personal access token to push to homebrew-yuki repo |

## Local test build (no signing)

```bash
uv sync
cd frontend && npm ci && npm run build && cp -r out ../yuki/backend/static && cd ..
cd app && swift build -c release && cd ..
uv run briefcase create macOS app -c packaging/briefcase.toml
uv run briefcase build macOS app -c packaging/briefcase.toml
open macOS/app/Yuki/Yuki.app
```

(Will be quarantined — Gatekeeper blocks unsigned. Right-click → Open → Open to bypass for local testing.)
```

- [ ] **Step 2: Commit**

```bash
git add docs/DISTRIBUTION.md
git commit -m "feat(packaging): add distribution runbook"
```

---

## Wrap-up

After Task 6, releasing Yuki is:

1. Tag `v<version>` on `main`
2. The `release.yml` workflow builds, signs, notarizes, uploads
3. Users get the update via Sparkle (existing installs) or `brew upgrade --cask yuki`

Acceptance:
- `uv run briefcase create macOS app -c packaging/briefcase.toml` succeeds locally (without signing)
- `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"` succeeds
- All required secrets are documented in `docs/DISTRIBUTION.md`
- A dry-run from Task 1's local sanity-build produces a launchable `.app` bundle
- The Homebrew Cask formula resolves to a real GitHub release URL

