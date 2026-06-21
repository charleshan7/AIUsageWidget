#!/bin/bash
# 安装并启动 AI 用量取数 Agent（LaunchAgent，登录自启 + 保活）。
# 用法：bash agent/install.sh        安装/更新并启动
#       bash agent/install.sh remove 卸载
set -euo pipefail

LABEL="com.charles.aiusage.agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
APP_SUPPORT="$HOME/Library/Application Support/AIUsageWidget"
TARGET="$APP_SUPPORT/usage-agent.py"
LOG="$HOME/Library/Logs/ai-usage-agent.log"
UID_NUM="$(id -u)"

if [ "${1:-}" = "remove" ]; then
    launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "✅ 已卸载 Agent。"
    exit 0
fi

SRC="$(cd "$(dirname "$0")" && pwd)/usage-agent.py"
mkdir -p "$APP_SUPPORT" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cp "$SRC" "$TARGET"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$TARGET</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG</string>
    <key>StandardErrorPath</key>
    <string>$LOG</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST"
launchctl kickstart -k "gui/$UID_NUM/$LABEL"

sleep 1
echo "✅ Agent 已安装并启动。"
echo "   端点: http://127.0.0.1:47615/usage"
echo "   日志: $LOG"
echo "   自测: curl -s http://127.0.0.1:47615/usage"
