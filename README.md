# AI 用量小组件（AIUsageWidget）

macOS 桌面小组件，展示 **Claude Code** 与 **Codex** 的 **5 小时**和**一周**用量
（百分比 + 重置倒计时，颜色按吃紧程度变化）。支持小 / 中 / 大三种尺寸。

## 架构

沙盒 Widget 只能联网，读不到本地数据，所以由一个**本地 Agent** 取数并通过
`127.0.0.1` 暴露给 Widget：

```
~/.codex/sessions/*.jsonl ─┐
  primary(5h)/secondary(周) ├─► usage-agent.py ──► http://127.0.0.1:47615/usage ──► Widget / App
Keychain(Claude Code 凭证)  ─┘   · Codex 读本地 session
                                · Claude 调 /api/oauth/usage（过期自动刷新并写回 Keychain）
```

- 数据全程不出本机，无云端。
- Codex：读本地 session 文件的 `rate_limits`。
- Claude Code：调 `api.anthropic.com/api/oauth/usage`，凭证取自 macOS Keychain。

## 安装

```bash
# 1) 构建 App + Widget
xcodegen generate
xcodebuild -scheme AIUsageWidget -configuration Release build

# 2) 安装后台取数 Agent（登录自启）
bash agent/install.sh

# 3) 打开 build 出的 AIUsageWidget.app，再到桌面添加小组件
```

卸载 Agent：`bash agent/install.sh remove`

## 配置

`~/.config/ai-usage-widget/config.json`（可选）：

```json
{ "port": 47615, "proxy": "http://127.0.0.1:7897", "cache_seconds": 60 }
```

改了端口要同步改 `Config.xcconfig` 里的 `AI_USAGE_ENDPOINT`。

设计细节见 [docs/superpowers/specs/2026-06-21-ai-usage-widget-design.md](docs/superpowers/specs/2026-06-21-ai-usage-widget-design.md)。
