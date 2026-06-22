#!/bin/sh
# 打出可分发的 DMG（ad-hoc 签名），自带后台服务安装脚本。
# 用法：sh release/package-dmg.sh [版本号]
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

# 后台取数 Agent（DMG 内自带，供安装脚本使用）
cp "$repo_root/agent/usage-agent.py" "$staging/usage-agent.py"

# 一键安装后台服务（双击运行）
cat > "$staging/① 安装后台服务.command" <<'CMDEOF'
#!/bin/bash
set -e
cd "$(dirname "$0")"
LABEL="com.charles.aiusage.agent"
APP_SUPPORT="$HOME/Library/Application Support/AIUsageWidget"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/ai-usage-agent.log"
TARGET="$APP_SUPPORT/usage-agent.py"
mkdir -p "$APP_SUPPORT" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cp "usage-agent.py" "$TARGET"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array><string>/usr/bin/python3</string><string>$TARGET</string></array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$LOG</string>
    <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLISTEOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
echo ""
echo "✅ 后台服务已安装并启动。"
echo "   现在可以打开 AIUsageWidget，然后在桌面添加小组件。"
echo "   （可关闭此窗口）"
CMDEOF
chmod +x "$staging/① 安装后台服务.command"

# 使用说明
cat > "$staging/使用说明.txt" <<'TXTEOF'
AI 用量小组件 安装步骤
======================

1) 把 AIUsageWidget.app 拖到「应用程序」。

2) 安装后台取数服务：
   右键点「① 安装后台服务.command」→ 打开 →（首次会提示来自未知开发者，点“打开”）。
   看到“✅ 后台服务已安装并启动”即可。

3) 打开 AIUsageWidget（菜单栏出现两道横条图标），再到桌面右键“编辑小组件”
   搜“AI 用量”添加。

首次打开 App 若提示“已损坏/无法打开”（ad-hoc 签名 + 下载隔离所致），在终端执行：
   xattr -dr com.apple.quarantine /Applications/AIUsageWidget.app

需要代理才能访问 api.anthropic.com 的用户：
   在 ~/.config/ai-usage-widget/config.json 写：
   { "proxy": "http://127.0.0.1:7897" }

数据全程在本机处理，不上传任何服务器。
TXTEOF

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
