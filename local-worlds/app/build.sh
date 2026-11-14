#!/bin/zsh
# Builds "Nate's Worlds.app" next to this script. The app runs ../thread/server.py, so it works only with this folder in place.
set -e
cd "$(dirname "$0")"
APP="Nate's Worlds.app"; rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
swiftc -O main.swift -o "$APP/Contents/MacOS/NatesWorlds" -framework Cocoa -framework WebKit
echo "$(cd ../thread && pwd)" > "$APP/Contents/Resources/root.txt"
# icon: icon_1024.png (from make_icon.py) -> .icns
ICONSET=$(mktemp -d)/AppIcon.iconset; mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s icon_1024.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) icon_1024.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
cat > "$APP/Contents/Info.plist" <<P
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Nate's Worlds</string>
<key>CFBundleDisplayName</key><string>Nate's Worlds</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundleIdentifier</key><string>local.natesworlds.app</string>
<key>CFBundleExecutable</key><string>NatesWorlds</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.2</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
P
codesign --force --sign - "$APP" 2>/dev/null || true
echo "built $APP"
