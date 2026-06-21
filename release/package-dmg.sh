#!/bin/sh
# 打出可分发的 DMG（ad-hoc 签名）。用法：sh release/package-dmg.sh [版本号]
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version=${1:-1.0.0}
build_root="$repo_root/build/ReleasePackage"
products="$build_root/DerivedData/Build/Products/Release"
source_app="$products/AIUsageWidget.app"
staging="$build_root/dmg-root"
app_name="AIUsageWidget.app"
output="$build_root/AIUsageWidget-v${version}.dmg"

cd "$repo_root"
xcodegen generate
xcodebuild -project AIUsageWidget.xcodeproj -scheme AIUsageWidget \
  -configuration Release -derivedDataPath "$build_root/DerivedData" build

rm -rf "$staging" "$output"
mkdir -p "$staging"
cp -R "$source_app" "$staging/$app_name"
ln -s /Applications "$staging/Applications"

codesign --force --sign - \
  --entitlements "$repo_root/Widget/Widget.entitlements" \
  "$staging/$app_name/Contents/PlugIns/AIUsageWidgetExtension.appex"
codesign --force --sign - \
  --entitlements "$repo_root/App/App.entitlements" \
  "$staging/$app_name"
codesign --verify --deep --strict --verbose=2 "$staging/$app_name"

hdiutil create -volname "AI Usage Widget" -srcfolder "$staging" \
  -ov -format UDZO "$output"

echo "$output"
