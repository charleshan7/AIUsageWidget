#!/bin/bash
# 编译并把 App 装到 /Applications。
#
# 为什么必须装到 /Applications：小组件宿主 App 如果直接从 build/DerivedData 里跑，
# 每次重新编译都会让 chronod 那边的小组件注册失效。失效后系统不再重绘卡片，
# 而卡片会一直挂着上次渲染的画面——倒计时文案是那一刻算好的，看上去完全合理，
# 实际可能是几天前的数字。2026-08-04 就是这么冻了 5 天没被发现。
set -e
cd "$(dirname "$0")"

DST=/Applications/AIUsageWidget.app
SRC=build/DerivedData/Build/Products/Release/AIUsageWidget.app

echo "==> 编译 Release"
xcodebuild -project AIUsageWidget.xcodeproj -scheme AIUsageWidget \
           -configuration Release -derivedDataPath build/DerivedData build \
           >/tmp/aiusage-build.log 2>&1 || { tail -30 /tmp/aiusage-build.log; exit 1; }

echo "==> 退出旧进程"
osascript -e 'tell application "AIUsageWidget" to quit' 2>/dev/null || true
sleep 2
pkill -f "AIUsageWidget.app/Contents/MacOS/AIUsageWidget" 2>/dev/null || true
sleep 1

echo "==> 安装到 $DST"
rm -rf "$DST"
cp -R "$SRC" "$DST"
codesign -v --deep --strict "$DST"

echo "==> 重建注册并重启小组件调度器"
LSR=/System/Library/Frameworks/CoreServices.framework/Versions/Current/Frameworks/LaunchServices.framework/Versions/Current/Support/lsregister
"$LSR" -u "$SRC" 2>/dev/null || true
"$LSR" -f -R -trusted "$DST"
killall chronod 2>/dev/null || true

echo "==> 启动"
sleep 2
open -a "$DST"

echo "完成。若菜单栏「开机自启动」是关的，勾一次即可绑定到新路径。"
