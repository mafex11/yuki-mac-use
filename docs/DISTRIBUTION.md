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
| `APPLE_APP_PASSWORD` | App-specific password for notarytool |
| `APPLE_DEVELOPER_ID` | Full "Developer ID Application: ..." string |
| `SPARKLE_ED25519_KEY` | Private ed25519 key for Sparkle update signing |
| `HOMEBREW_TAP_TOKEN` | PAT to push to homebrew-yuki repo |

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
