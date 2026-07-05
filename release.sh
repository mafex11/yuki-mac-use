#!/usr/bin/env bash
# Build a distributable Yuki.app (Swift binary + bundled Python) and zip it.
# Usage: ./release.sh <version>   e.g. ./release.sh 0.1.0
set -euo pipefail

VERSION="${1:?usage: ./release.sh <version>}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
BUILD="$ROOT/build"
APP="$BUILD/Yuki.app"
CONTENTS="$APP/Contents"
RES="$CONTENTS/Resources"
PYDIR="$RES/python"
PYVER="3.12"

# python-build-standalone release (astral-sh fork, was indygreg)
PBS_TAG="20241016"
PBS_PY="3.12.7"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/cpython-${PBS_PY}+${PBS_TAG}-aarch64-apple-darwin-install_only.tar.gz"

echo "==> Clean build dir"
rm -rf "$BUILD"
mkdir -p "$CONTENTS/MacOS" "$RES"

echo "==> Build Swift release binary"
( cd "$ROOT/app" && swift build -c release )
cp "$ROOT/app/.build/release/Yuki" "$CONTENTS/MacOS/Yuki"
chmod +x "$CONTENTS/MacOS/Yuki"

echo "==> Copy Info.plist"
cp "$ROOT/app/Yuki/Info.plist" "$CONTENTS/Info.plist"

echo "==> Copy app icon"
cp "$ROOT/packaging/icon/Yuki.icns" "$RES/Yuki.icns"

echo "==> Fetch python-build-standalone ($PBS_PY)"
curl -fsSL "$PBS_URL" -o "$BUILD/python.tar.gz"
mkdir -p "$PYDIR"
tar -xzf "$BUILD/python.tar.gz" -C "$BUILD"
# The tarball extracts to a 'python/' dir; move its contents into PYDIR.
cp -R "$BUILD/python/." "$PYDIR/"
rm -rf "$BUILD/python" "$BUILD/python.tar.gz"

echo "==> Install yuki + deps into the bundled interpreter"
SITE="$PYDIR/lib/python${PYVER}/site-packages"
"$PYDIR/bin/python3" -m pip install --upgrade pip >/dev/null
# Install runtime deps from pyproject via uv export → requirements, into the bundle.
# Filter out the local project line (-e .) that uv export emits.
( cd "$ROOT" && uv export --frozen --no-dev | grep -v '^-e \.' > "$BUILD/requirements.txt" )
"$PYDIR/bin/python3" -m pip install --no-warn-script-location \
    --target "$SITE" -r "$BUILD/requirements.txt"
# Copy the yuki package source itself into site-packages.
cp -R "$ROOT/yuki" "$SITE/yuki"

echo "==> Preload tiktoken BPE (offline support)"
TIKTOKEN_CACHE_DIR="$RES/tiktoken" \
  "$PYDIR/bin/python3" -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" \
  || echo "warning: tiktoken preload failed (will download at first use)"

# Deep sign the FULLY-ASSEMBLED bundle. This MUST be the last step before
# zipping: `swift build` only linker-signs the executable, and copying
# Python/resources in afterward breaks that seal ("code has no resources but
# signature indicates they must be present"). A broken seal makes macOS refuse
# to persist the Accessibility (TCC) grant — you grant it, it silently reverts.
#
# Identity matters: with a REAL certificate (Apple Development / Developer ID)
# the designated requirement anchors to the cert + identifier, which is STABLE
# across rebuilds — TCC grants and Keychain ACLs then survive upgrades.
# Ad-hoc (-) signatures are cdhash-only: every build is a "different app", so
# users re-grant Accessibility + re-authorize Keychain on every update.
# Override with YUKI_SIGN_IDENTITY; auto-detects a cert; falls back to ad-hoc.
IDENTITY="${YUKI_SIGN_IDENTITY:-}"
if [ -z "$IDENTITY" ]; then
  IDENTITY=$(security find-identity -v -p codesigning 2>/dev/null \
    | awk -F'"' '/Apple Development|Developer ID Application/ {print $2; exit}')
fi
if [ -n "$IDENTITY" ]; then
  echo "==> Deep sign with identity: $IDENTITY"
  codesign --force --deep --timestamp=none \
    --sign "$IDENTITY" --identifier com.yuki.app "$APP" \
    || { echo "identity signing failed; falling back to ad-hoc"; \
         codesign --force --deep --sign - --identifier com.yuki.app "$APP"; }
else
  echo "==> Deep ad-hoc sign (no signing identity found)"
  codesign --force --deep --sign - --identifier com.yuki.app "$APP"
fi
codesign --verify --deep --strict "$APP" \
  && echo "    signature: valid (deep seal over all contents)" \
  || { echo "ERROR: bundle signature failed to verify"; exit 1; }

echo "==> Zip the app"
( cd "$BUILD" && ditto -c -k --keepParent "Yuki.app" "Yuki-${VERSION}.zip" )
SHA=$(shasum -a 256 "$BUILD/Yuki-${VERSION}.zip" | cut -d' ' -f1)

echo ""
echo "==> Built $BUILD/Yuki-${VERSION}.zip"
echo "    sha256: $SHA"
echo "    size:   $(du -h "$BUILD/Yuki-${VERSION}.zip" | cut -f1)"
echo ""
echo "Next: gh release create v${VERSION} build/Yuki-${VERSION}.zip"
echo "Then update homebrew-tap Casks/yuki.rb version+sha256 (C2)."
