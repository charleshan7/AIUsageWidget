# AGENTS.md — AI 用量小组件开发指南

给接手本项目的 AI 编程助手（Claude Code / Codex / Cursor 等）的说明。用户可读文档见 README.md；本文件只写开发者需要、但代码里看不出来的东西。

## 项目一句话

macOS 菜单栏 App + WidgetKit 桌面小组件，显示 Claude Code 与 Codex 的 5 小时 / 一周用量、Token 消耗统计和订阅性价比（「本月羊毛」）。已开源（MIT）。

## 架构（为什么是这个形状）

**沙盒小组件读不到本地文件和 Keychain**——这是整个架构的成因。取数全部由非沙盒本地 Agent（`agent/usage-agent.py`，LaunchAgent `com.charles.aiusage.agent` 登录自启）完成，通过 `http://127.0.0.1:47615/usage` 供给组件和 App。改任何取数逻辑都改 Agent，不要试图让组件直接读文件。

- **Codex 取数**：主路是实时接口 `GET chatgpt.com/backend-api/wham/usage`（Bearer token 取自 `~/.codex/auth.json`，`ChatGPT-Account-Id` 从 id_token JWT 解出）；失败回退扫 `~/.codex/sessions/**/*.jsonl` 的 `rate_limits` 快照。快照模式下"不用 Codex 数字就不动"是固有限制。
- **Claude Code 取数**：`GET api.anthropic.com/api/oauth/usage`（header `anthropic-beta: oauth-2025-04-20`），凭证在 Keychain `Claude Code-credentials`。access token 过期用 refreshToken 刷新。**刷新会轮换 refreshToken，必须按原结构写回 Keychain，否则用户的 `claude` CLI 登录直接失效**——这是本仓库最容易造成实际损害的坑。
- **外观/配置下发**：沙盒组件读不到本地偏好，所以主题等设置由 App GET 到 Agent 的 `/config?theme=`，Agent 随 `/usage` 下发。WidgetKit 不认 `preferredColorScheme`，Palette 是 light/dark 两套 struct 显式选色。

## 构建与运行

```bash
xcodegen generate
xcodebuild -scheme AIUsageWidget -configuration Release build
bash agent/install.sh        # 装/更新 LaunchAgent；卸载: bash agent/install.sh remove
```

App 运行的是 `build/DerivedData/Build/Products/Release/` 下的产物；改完重建 + 重启 App 即生效。ad-hoc 签名，无需开发者账号。

## 关键决策与踩过的坑（勿重蹈）

1. **Token 统计必须按 `message.id` 去重（Claude 侧）**：流式分块会把同一消息写多行，续接/compact 会把历史复制进新文件，直接累加会虚高 61%。synthetic 消息要跳过。校准基准：与 ccusage 的 message 级去重结果吻合。
2. **Codex 的 `cached_input` 是 `input_tokens` 的子集**（OpenAI 语义），不是独立计费项。ccusage 把它当独立项加成了约 2 倍——别学它。
3. **Codex 现役模型是 gpt-5.5 / gpt-5.6-sol**，官方牌价 $5/$0.5/$30（入/缓存/出），比老 GPT-5 档贵 4 倍，价格表别用错。
4. **Claude refreshToken 是绝对 30 天有效期**（从 `/login` 那天起算，刷 access token 续不了它的命）。过期后 Agent 返回 last-good 数据并带 `stale: true`，UI 显示红色「已过期」角标 + 数据变灰 + 面板重登提示。诊断：`curl localhost:47615/usage` 看 claude 是否 `"stale": true`；修复只能让用户在终端 `claude` 里 `/login`。
5. **刷新 refreshToken 必须串行——这个坑真的把用户凭证搞坏过两次。** 服务是 `ThreadingHTTPServer`，而 `reloadAllTimelines()` 会同时唤醒小/中/大三个组件来取数。早期版本 `Snapshot.get()` 和 `read_claude()` 都没锁，多个线程各拿同一个 refreshToken 去刷新，而**每次刷新都会轮换 refreshToken**，后发的那次让先写回的那份当场作废，Keychain 里就留下一个死 token，用户只能重新登录。现在靠 `_REFRESH_LOCK`（串行 + 锁内重读 Keychain）和 `Snapshot` 的双检锁兜住，回归测试见 `agent/tests/`。**动取数并发相关的代码前先跑那两个测试。**
6. **凭证坏掉的两种形态要分清**：`Refresh token expired` = 30 天到期（见第 4 条）；`Refresh token not found or invalid` = 被轮换作废（第 5 条的后果）。另有一种是 `refreshToken` 变成空字符串——`claude` 自己刷新失败后会清空它，此时拿空串去刷只会换来一句莫名其妙的 `Invalid request format`，所以 `_ensure_token` 里提前拦掉并直接报 `relogin`。还有一种是 `Claude Code-credentials` 条目里整个没有 `claudeAiOauth`（只剩 `mcpOAuth`）——独立 CLI 已登出，同样报 `relogin`。报错信息务必带上失败阶段（keychain/refresh/usage）和响应体，否则诊断只能靠猜。
7. **让用户重登时，必须说明「在 Terminal.app 里用独立 CLI 登录」。** Claude 桌面版内嵌的 Claude Code（`CLAUDE_CODE_ENTRYPOINT=claude-desktop`）认证由桌面版托管，token 存进 `Claude Safe Storage`，在里面 `/login` 只更新 `~/.claude.json` 的账号信息，**一个字节都不写 `Claude Code-credentials`**——而 Agent 读的正是后者。曾因为这个让用户白登了两次。验证登录是否落到位：`security find-generic-password -s "Claude Code-credentials" | grep mdat`，时间戳是刚才即成功。
8. 代理默认直连；用户如需代理，写 `~/.config/ai-usage-widget/config.json` 的 `proxy` 字段，不要硬编码。

## 数据文件

- Token 统计增量缓存：`~/.config/ai-usage-widget/token-cache.json`（文件级 (mtime,size) 缓存，5 分钟重算）
- UI 偏好：`~/.config/ai-usage-widget/ui.json`

## 提交约定

main 分支直推，commit 信息中文为主。发布打包用 `release/package-dmg.sh`。
