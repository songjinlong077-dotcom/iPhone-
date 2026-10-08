#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$IOS_DIR/build"
DERIVED_DIR="$BUILD_DIR/DerivedData"
LOG_DIR="$BUILD_DIR/logs"
OUTPUT_DIR="$IOS_DIR/output"

rm -rf "$BUILD_DIR" "$OUTPUT_DIR"
mkdir -p "$LOG_DIR" "$OUTPUT_DIR"

xcodebuild -version | tee "$LOG_DIR/xcode-version.txt"
cd "$IOS_DIR"
xcodegen generate

SIMULATOR_UDID="$(xcrun simctl list devices available -j | python3 -c '
import json, sys
data = json.load(sys.stdin)
for runtime, devices in data.get("devices", {}).items():
    for device in devices:
        if device.get("isAvailable") and device.get("name", "").startswith("iPhone"):
            print(device["udid"])
            raise SystemExit(0)
raise SystemExit("No available iPhone simulator")
')"
echo "Selected simulator: $SIMULATOR_UDID" | tee "$LOG_DIR/simulator.txt"

set -o pipefail
xcodebuild \
  -project "$IOS_DIR/VideoDownloader.xcodeproj" \
  -scheme VideoDownloader \
  -configuration Debug \
  -destination "platform=iOS Simulator,id=$SIMULATOR_UDID" \
  -derivedDataPath "$DERIVED_DIR-simulator" \
  CODE_SIGNING_ALLOWED=NO \
  test | tee "$LOG_DIR/simulator-test.log"

xcodebuild \
  -project "$IOS_DIR/VideoDownloader.xcodeproj" \
  -scheme VideoDownloader \
  -configuration Release \
  -sdk iphoneos \
  -destination "generic/platform=iOS" \
  -derivedDataPath "$DERIVED_DIR-device" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGN_IDENTITY="" \
  build | tee "$LOG_DIR/device-build.log"

APP_PATH="$(find "$DERIVED_DIR-device/Build/Products/Release-iphoneos" -maxdepth 1 -type d -name '*.app' -print -quit)"
if [[ -z "$APP_PATH" || ! -d "$APP_PATH" ]]; then
  echo "No device .app bundle was produced" >&2
  exit 1
fi

EXECUTABLE_NAME="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$APP_PATH/Info.plist")"
EXECUTABLE_PATH="$APP_PATH/$EXECUTABLE_NAME"
if [[ ! -f "$EXECUTABLE_PATH" ]]; then
  echo "App executable is missing: $EXECUTABLE_PATH" >&2
  exit 1
fi

ARCHITECTURES="$(lipo -archs "$EXECUTABLE_PATH")"
echo "Device architectures: $ARCHITECTURES" | tee "$LOG_DIR/device-architectures.txt"
if ! grep -qw arm64 <<<"$ARCHITECTURES"; then
  echo "The device app does not contain arm64" >&2
  exit 1
fi

codesign --remove-signature "$APP_PATH" 2>/dev/null || true
rm -rf "$OUTPUT_DIR/Payload"
mkdir -p "$OUTPUT_DIR/Payload"
ditto "$APP_PATH" "$OUTPUT_DIR/Payload/$(basename "$APP_PATH")"

IPA_NAME="VideoDownloader-v4-unsigned.ipa"
cd "$OUTPUT_DIR"
ditto -c -k --sequesterRsrc --keepParent Payload "$IPA_NAME"
unzip -t "$IPA_NAME" | tee "$LOG_DIR/ipa-integrity.txt"
unzip -l "$IPA_NAME" | tee "$LOG_DIR/ipa-contents.txt"
shasum -a 256 "$IPA_NAME" | tee "$IPA_NAME.sha256"

if ! unzip -l "$IPA_NAME" | grep -q 'Payload/.*\.app/Info.plist'; then
  echo "IPA does not contain Payload/*.app/Info.plist" >&2
  exit 1
fi

echo "IPA_PATH=$OUTPUT_DIR/$IPA_NAME"
