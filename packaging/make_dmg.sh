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
