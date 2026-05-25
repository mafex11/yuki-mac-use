#!/usr/bin/env bash
set -euo pipefail

DMG="${1:?usage: sign.sh <dmg> <ed25519_priv_key_path>}"
KEY="${2:?usage: sign.sh <dmg> <ed25519_priv_key_path>}"

if ! command -v sparkle-sign >/dev/null 2>&1; then
  echo "Install Sparkle binaries (https://sparkle-project.org) and ensure 'sign_update' is on PATH" >&2
  exit 1
fi

sparkle-sign "$DMG" "$KEY"
