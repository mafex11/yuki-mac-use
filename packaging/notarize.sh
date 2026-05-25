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
