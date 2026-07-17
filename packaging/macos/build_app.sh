#!/bin/zsh
# Build and install ytk.app — the stable TCC identity for the hub daemon.
#
# The app is a branded launcher: launchd runs its stub binary, the stub
# spawns `ytk ui` as a child, and macOS attributes permissions (Full Disk
# Access shows "ytk" with the brass icon) to the bundle. ytk code updates
# via `uv tool install --reinstall` NEVER require rebuilding this app.
#
# IMPORTANT: the app is ad-hoc signed, so TCC keys on the built binary —
# REBUILDING RESETS THE FULL DISK ACCESS GRANT. The script therefore
# refuses to overwrite an existing install unless passed --force.
#
#   ./packaging/macos/build_app.sh [--force]

set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="ytk"
BUNDLE_ID="com.pablomoli.ytk"
DEST="/Applications/${APP_NAME}.app"
[[ -w /Applications ]] || DEST="$HOME/Applications/${APP_NAME}.app"

if [[ -d "$DEST" && "${1:-}" != "--force" ]]; then
    echo "$DEST exists — rebuilding would reset its Full Disk Access grant."
    echo "Run with --force if you really mean it."
    exit 1
fi

BUILD="$(mktemp -d)/${APP_NAME}.app"
mkdir -p "$BUILD/Contents/MacOS" "$BUILD/Contents/Resources"

clang -O2 -Wall -o "$BUILD/Contents/MacOS/ytk-hub" ytk-hub.c
uv run python make_icon.py "$BUILD/Contents/Resources"

cat > "$BUILD/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>ytk-hub</string>
    <key>CFBundleIdentifier</key><string>${BUNDLE_ID}</string>
    <key>CFBundleName</key><string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key><string>${APP_NAME}</string>
    <key>CFBundleIconFile</key><string>ytk.icns</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>0.1.0</string>
    <key>LSUIElement</key><true/>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict>
</plist>
PLIST

codesign --force --sign - "$BUILD"
rm -rf "$DEST"
mkdir -p "$(dirname "$DEST")"
mv "$BUILD" "$DEST"
echo "installed $DEST"

# Point the LaunchAgent at the stub (idempotent).
PLIST_PATH="$HOME/Library/LaunchAgents/com.ytk.hub.plist"
if [[ -f "$PLIST_PATH" ]]; then
    /usr/libexec/PlistBuddy -c "Delete :ProgramArguments" "$PLIST_PATH"
    /usr/libexec/PlistBuddy -c "Add :ProgramArguments array" "$PLIST_PATH"
    /usr/libexec/PlistBuddy -c "Add :ProgramArguments:0 string ${DEST}/Contents/MacOS/ytk-hub" "$PLIST_PATH"
    launchctl bootout "gui/$(id -u)/com.ytk.hub" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
    echo "LaunchAgent now runs the app stub; hub restarted."
fi

echo
echo "Next: System Settings > Privacy & Security > Full Disk Access >"
echo "add ${DEST} (shows as '${APP_NAME}' with the brass icon), then:"
echo "  launchctl kickstart -k gui/$(id -u)/com.ytk.hub"
