# AI 用量小组件（AIUsageWidget）设计文档

日期：2026-06-21
作者：Charles + Claude

## 目标

一个 macOS 桌面小组件，展示 **Claude Code** 和 **Codex** 两个 AI 编程工具的
**5 小时滚动窗口用量**和**一周用量**（百分比 + 重置倒计时）。形态和现有的
`~/WorldCupWidget` 一样：WidgetKit App + Widget 扩展 + 共享代码，ad-hoc 签名、沙盒。

## 数据来源（已实测验证）

| 工具 | 5 小时 | 一周 | 取数方式 |
|------|--------|------|----------|
| Codex | `primary`（window 300 分钟） | `secondary`（window 10080 分钟） | 读本地 `~/.codex/sessions/**/*.jsonl`，取最新一条 `rate_limits`：`used_percent` + `resets_at`(unix 秒)。纯本地、零联网。 |
| Claude Code | `five_hour.utilization` | `seven_day.utilization` | 调 `GET https://api.anthropic.com/api/oauth/usage`，Header `Authorization: Bearer <token>` + `anthropic-beta: oauth-2025-04-20`。`resets_at` 为 ISO8601。 |

### Claude Code token 机制（关键、不显然）

- 凭证在 **macOS Keychain**：service `Claude Code-credentials`，blob 为 JSON，路径
  `claudeAiOauth.{accessToken,refreshToken,expiresAt,subscriptionType}`。
- access token 会过期（`expiresAt`，毫秒）。过期时需用 refreshToken 刷新：
  `POST https://api.anthropic.com/v1/oauth/token`，body
  `{"grant_type":"refresh_token","refresh_token":<rt>,"client_id":"9d1c250a-e61b-44d9-88ed-5944d1962f5e"}`。
- **刷新会轮换 refreshToken**，所以刷新后**必须把新凭证按完全相同的 JSON 结构写回
  Keychain**（`security add-generic-password -U`），否则 Claude Code 自身下次刷新会失效、
  用户被迫重新登录。
- 实测响应示例：`five_hour.utilization=26`、`seven_day.utilization=20`，`spend`/`limits` 等字段忽略。
- 代理：用户的 `claude` 走 `http://127.0.0.1:7897`。Anthropic 调用默认走该代理，可配置。

## 核心矛盾与架构

沙盒 Widget **只能联网**，读不到本地 Codex 文件，也读不到 Keychain。WorldCup 也是
ad-hoc 签名、**没有 App Group**（见 `SharedStore.swift` 注释），它的 Widget 直接在
TimelineProvider 里 `URLSession` 打远程 Worker。

我们的数据是本地的，所以引入一个**非沙盒的本地 Agent**做桥接，对 Widget 暴露一个
**127.0.0.1 本地 HTTP 端点**（Widget 用 `network.client` 即可访问，数据不出本机）。

```
~/.codex/sessions/*.jsonl ─┐
  primary(5h)/secondary(周) ├─► usage-agent.py ──► http://127.0.0.1:47615/usage ──► Widget / App
Keychain(Claude Code-       │   · 读 Codex 最新 rate_limits         (URLSession GET)
  credentials)             ─┘   · Claude: 读token→过期则刷新+写回→/usage
                                · 合并 JSON，60s 缓存，本地 http.server
```

### 组件与职责

1. **`agent/usage-agent.py`** — 纯 Python 标准库（`urllib`/`http.server`/`json`/`subprocess`）。
   - 读 Codex 最新 `rate_limits`（newest-first 扫 session 文件，找到第一条即停）。
   - Claude：读 Keychain → `expiresAt` 临近则刷新并写回 → 调 `/api/oauth/usage`。
   - 合并为统一 JSON（见下），`resets_at` 一律归一化成 unix 秒。
   - 起 `127.0.0.1:<port>` HTTP 服务，`GET /usage` 返回 JSON；数据 60 秒内存缓存。
   - 单产品失败时该产品 `ok:false` + `error`，另一个照常返回；尽量复用上次成功值。
   - 配置：`~/.config/ai-usage-widget/config.json`（可选）`{"port":47615,"proxy":"http://127.0.0.1:7897"}`。
2. **LaunchAgent** `~/Library/LaunchAgents/com.charles.aiusage.agent.plist` —
   `RunAtLoad` + `KeepAlive`，登录自启、保活；日志输出到 `~/Library/Logs/ai-usage-agent.log`。
3. **Widget 扩展** — 照搬 WorldCup 的 Provider/RefreshIntent/卡片结构，endpoint 改为本地。
4. **宿主 App** — 极简窗口：4 个数字 + Agent 状态 +「安装 Agent / 刷新」按钮，`LSUIElement`。

### 统一 JSON 契约（Agent → 前端）

```json
{
  "updated": 1782000000,
  "claude": {
    "ok": true, "plan": "pro",
    "five_hour": { "percent": 26, "resets_at": 1782001200 },
    "seven_day": { "percent": 20, "resets_at": 1782500000 }
  },
  "codex": {
    "ok": true,
    "five_hour": { "percent": 35, "resets_at": 1782001000 },
    "seven_day": { "percent": 23, "resets_at": 1782580000 }
  }
}
```
失败产品形如 `{"ok": false, "error": "未登录 / 刷新失败"}`。

## UI 设计

支持 **systemSmall / systemMedium / systemLarge** 三种尺寸（用户可任选）。

每个产品两条**横向进度条**：`5 小时` 和 `一周`，右侧百分比，下方重置倒计时。
进度条填充色按吃紧程度（severity）：

| 区间 | 含义 | 颜色 |
|------|------|------|
| < 50% | 富余 | 绿（success） |
| 50–79% | 留意 | 黄（warning） |
| ≥ 80% | 吃紧 | 红（danger） |

- **小卡**：两个产品各两条迷你进度条 + 百分比（省略重置时间）。
- **中卡**：左右两列 Claude / Codex，各含 5h、周进度条 + 百分比 + 「约 X 小时后重置」。
- **大卡**：上下两段，进度条更大，含百分比 + 「X 小时后重置 · 绝对时间」。
- 右上角放刷新按钮（`AppIntent`，复用 WorldCup 的 `RefreshIntent` 模式）。
- 背景沿用 WorldCup 的深色渐变 `containerBackground`。

### 异常态

- Agent 未运行 / 端点不通：Widget 显示上次快照或「未连接 · 请启动 Agent」提示。
- Claude 未登录或刷新失败：该产品显示「未登录」，Codex 仍正常显示。
- Codex 无 session（从没用过）：该产品显示「无数据」。

## 工程结构（新建独立项目，复用 WorldCup 模板）

```
~/AIUsageWidget/
  project.yml                 # xcodegen，bundle 前缀 com.charles.aiusage
  Config.xcconfig             # AI_USAGE_ENDPOINT = http:/$()/127.0.0.1:47615/usage
  Release.xcconfig
  App/  (UsageApp.swift, Info.plist[+NSAllowsLocalNetworking], App.entitlements, Assets)
  Widget/ (UsageWidget.swift, UsageWidgetBundle.swift, UsageWidgetViews.swift,
           Info.plist[+NSAllowsLocalNetworking], Widget.entitlements, Assets)
  Shared/ (UsageModel.swift, UsageAPI.swift, SharedStore.swift)
  agent/  (usage-agent.py, com.charles.aiusage.agent.plist.template, install.sh)
  release/ (package-dmg.sh)
  docs/superpowers/specs/2026-06-21-ai-usage-widget-design.md
```

- Bundle：App `com.charles.aiusage`，Widget `com.charles.aiusage.widget`。
- 签名：ad-hoc（`CODE_SIGN_STYLE Automatic` + 空 team；打包用 `codesign --sign -`），同 WorldCup。
- 部署目标 macOS 14.0。
- ATS：App 与 Widget 的 Info.plist 加
  `NSAppTransportSecurity > NSAllowsLocalNetworking = true`（仅放行本机回环 http）。
- Endpoint 经 xcconfig 注入 Info.plist 键 `AIUsageEndpoint`，Swift 侧从 `Bundle` 读。

## 构建与安装流程

1. `xcodegen generate` 生成 `.xcodeproj`。
2. `xcodebuild -scheme AIUsageWidget -configuration Release build`。
3. 运行 `agent/install.sh`：把 `usage-agent.py` 安装到固定路径、生成并 `launchctl load`
   LaunchAgent plist。
4. 打开 App → 添加桌面小组件。

## 已知注意点

- LaunchAgent 首次访问 Keychain 可能弹一次授权框，点「始终允许」即可。
- 代理不可用时 Claude 调用会失败（与 `claude` 同条件）；可在 config 关闭代理。
- 凭证备份留在 `~/.claude/.credentials.keychain-backup.json`（验证阶段生成，可保留）。

## 非目标（YAGNI）

- 不做云端 Worker、不做历史趋势图、不做 token 绝对数/金额、不做菜单栏常驻。
