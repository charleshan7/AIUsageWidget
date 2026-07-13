#!/usr/bin/env python3
"""AI 用量小组件 - 本地取数 Agent。

读取 Codex（本地 session 文件）与 Claude Code（OAuth /usage 接口）的
5 小时 / 一周用量，合并成统一 JSON，通过 127.0.0.1 本地 HTTP 暴露给沙盒 Widget。

纯标准库，无第三方依赖。兼容 Python 3.9+。

用法：
    python3 usage-agent.py            # 起 HTTP 服务（LaunchAgent 用这个）
    python3 usage-agent.py --once     # 取一次数据打印 JSON 后退出（自测用）
"""
import json
import os
import sys
import time
import glob
import base64
import getpass
import threading
import subprocess
import datetime
import urllib.request
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEYCHAIN_SERVICE = "Claude Code-credentials"
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
TOKEN_URL = "https://api.anthropic.com/v1/oauth/token"
OAUTH_BETA = "oauth-2025-04-20"

# 公开默认：直连（不走代理）。需要代理的用户在 config.json 或 HTTPS_PROXY 里填。
DEFAULTS = {"port": 47615, "proxy": None, "cache_seconds": 60}

# ---------------------------------------------------------------- 配置

def load_config():
    cfg = dict(DEFAULTS)
    path = os.path.expanduser("~/.config/ai-usage-widget/config.json")
    try:
        with open(path) as fh:
            cfg.update(json.load(fh))
    except FileNotFoundError:
        pass
    except Exception as e:
        sys.stderr.write("config 读取失败，用默认值: %r\n" % e)
    # 环境变量代理优先（LaunchAgent 里可注入）
    env_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if env_proxy:
        cfg["proxy"] = env_proxy
    return cfg

def make_opener(proxy):
    if proxy:
        handler = urllib.request.ProxyHandler({"https": proxy, "http": proxy})
    else:
        handler = urllib.request.ProxyHandler({})
    return urllib.request.build_opener(handler)

# ---------------------------------------------------------------- 时间

def iso_to_unix(s):
    if not s:
        return None
    try:
        s = s.replace("Z", "+00:00")
        return int(datetime.datetime.fromisoformat(s).timestamp())
    except Exception:
        return None

# ---------------------------------------------------------------- Codex

CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"

def read_codex(opener):
    """优先使用完整的实时窗口；不完整响应才回退本地一周快照。"""
    live = _codex_live(opener)
    # 未能从实时接口识别出一周窗口时，才使用本地兜底。_codex_live 会根据
    # limit_window_seconds 处理「primary 本身就是一周」的账号响应。
    if live is not None and live.get("five_hour") is not None and live.get("seven_day") is not None:
        return live

    fallback = _codex_from_files()
    if fallback.get("ok"):
        if live and live.get("plan"):
            fallback["plan"] = live["plan"]
        return fallback

    if live is not None:
        live["five_hour"] = {"percent": 0, "resets_at": None}
        return live
    return fallback


def _codex_account_id(auth):
    """从 id_token 解出 chatgpt_account_id（用于 ChatGPT-Account-Id 头选账号）。"""
    try:
        tok = auth["tokens"]["id_token"]
        seg = tok.split(".")[1]
        seg += "=" * (-len(seg) % 4)
        payload = json.loads(base64.urlsafe_b64decode(seg.encode()))
        return payload.get("https://api.openai.com/auth", {}).get("chatgpt_account_id")
    except Exception:
        return None


def _codex_live(opener):
    """调 ChatGPT 后端的 wham/usage，拿当前账号的实时 5h / 周用量。"""
    try:
        auth = json.load(open(os.path.expanduser("~/.codex/auth.json")))
        tok = auth.get("tokens", {}).get("access_token")
        if not tok:
            return None
        headers = {"Authorization": "Bearer %s" % tok, "User-Agent": "codex-cli"}
        acct = _codex_account_id(auth)
        if acct:
            headers["ChatGPT-Account-Id"] = acct
        req = urllib.request.Request(CODEX_USAGE_URL, headers=headers)
        j = _open_json(opener, req)
        rl = j.get("rate_limit") or {}
        primary = rl.get("primary_window")
        secondary = rl.get("secondary_window")

        # 有些账号只返回一个 7 天窗口，却放在 primary_window（secondary 为 null）。
        # 不能按字段名把它展示成 5 小时；按窗口时长映射到一周，并将 5 小时归零。
        if _codex_window_seconds(primary) >= 6 * 24 * 3600:
            five_hour = {"percent": 0, "resets_at": None}
            seven_day = _codex_live_win(primary)
        else:
            five_hour = _codex_live_win(primary)
            seven_day = _codex_live_win(secondary)
        return {"ok": True,
                "plan": j.get("plan_type"),
                "five_hour": five_hour,
                "seven_day": seven_day}
    except Exception:
        return None


def _codex_live_win(w):
    if not isinstance(w, dict):
        return None
    ra = w.get("reset_at")
    return {"percent": round(w.get("used_percent") or 0),
            "resets_at": int(ra) if ra else None}


def _codex_window_seconds(w):
    if not isinstance(w, dict):
        return 0
    try:
        return int(w.get("limit_window_seconds") or 0)
    except (TypeError, ValueError):
        return 0


def _codex_from_files():
    """回退：只使用本地快照中的一周窗口。

    多个并发会话时，文件 mtime 最新的那条可能是额度耗尽写的 primary/secondary 全 null
    的退化记录（limit_id="premium"），或比别的会话更旧。所以按每条 rate_limits 事件自身
    的 timestamp 全局取最新。注意：本地文件不带账号 id，多账号时可能串到别的账号。

    primary（5 小时）是 CLI 写入的临时限额快照，实时接口不可用时不能可靠代表当前
    窗口；此降级路径固定返回 0%，避免把过期的临时用量误报为实时消耗。secondary
    （一周）仍按最新可用快照显示。
    """
    pattern = os.path.expanduser("~/.codex/sessions/**/*.jsonl")
    files = sorted(glob.glob(pattern, recursive=True), key=os.path.getmtime, reverse=True)
    best_p = ("", None)   # (timestamp, primary window)
    best_s = ("", None)
    for path in files[:40]:
        try:
            with open(path, errors="ignore") as fh:
                for line in fh:
                    if '"rate_limits"' not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    rl = _find_key(obj, "rate_limits")
                    if not isinstance(rl, dict):
                        continue
                    ts = obj.get("timestamp") or ""
                    p, s = rl.get("primary"), rl.get("secondary")
                    if isinstance(p, dict) and ts > best_p[0]:
                        best_p = (ts, p)
                    if isinstance(s, dict) and ts > best_s[0]:
                        best_s = (ts, s)
        except Exception:
            continue
    if best_p[1] is None and best_s[1] is None:
        return {"ok": False, "error": "无数据（还没用过 Codex？）"}
    return {"ok": True,
            "five_hour": {"percent": 0, "resets_at": None},
            "seven_day": _codex_win(best_s[1]),
            "plan": _codex_plan()}


def _codex_win(w):
    """Codex 窗口 → {percent, resets_at}；窗口已过重置点（旧快照作废）显示 0%。"""
    if not isinstance(w, dict):
        return None
    ra = int(w["resets_at"]) if w.get("resets_at") else None
    if ra is not None and ra < time.time():
        return {"percent": 0, "resets_at": None}
    return {"percent": round(w.get("used_percent") or 0), "resets_at": ra}


def _codex_plan():
    """从 ~/.codex/auth.json 的 id_token 里解出套餐名（plus / pro / business…）。"""
    try:
        d = json.load(open(os.path.expanduser("~/.codex/auth.json")))
        tok = d.get("tokens", {}).get("id_token")
        if not tok:
            return None
        seg = tok.split(".")[1]
        seg += "=" * (-len(seg) % 4)
        payload = json.loads(base64.urlsafe_b64decode(seg.encode()))
        return payload.get("https://api.openai.com/auth", {}).get("chatgpt_plan_type")
    except Exception:
        return None


def _find_key(o, key):
    if isinstance(o, dict):
        if key in o:
            return o[key]
        for v in o.values():
            r = _find_key(v, key)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_key(v, key)
            if r is not None:
                return r
    return None

# ---------------------------------------------------------------- Claude

def _keychain_account():
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE],
                             capture_output=True, text=True).stdout
        for line in out.splitlines():
            line = line.strip()
            if line.startswith('"acct"'):
                return line.split('=', 1)[1].strip().strip('"')
    except Exception:
        pass
    return getpass.getuser()

def _keychain_read(acct):
    r = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", acct, "-w"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("读不到 Keychain 凭证（Claude Code 未登录？）")
    return json.loads(r.stdout.strip())

def _keychain_write(acct, cred):
    r = subprocess.run(["security", "add-generic-password", "-U",
                        "-s", KEYCHAIN_SERVICE, "-a", acct, "-w", json.dumps(cred)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write("写回 Keychain 失败: %s\n" % r.stderr)

def _open_json(opener, req, attempts=3):
    """打开请求并解析 JSON；对连接级抖动（SSL/超时/代理断连）重试，HTTP 错误不重试。"""
    last = None
    for i in range(attempts):
        try:
            with opener.open(req, timeout=25) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            last = e
            time.sleep(0.5 * (i + 1))
    raise last

def _refresh(opener, refresh_token):
    body = json.dumps({"grant_type": "refresh_token",
                       "refresh_token": refresh_token,
                       "client_id": OAUTH_CLIENT_ID}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "ai-usage-agent/1.0"})
    return _open_json(opener, req)

def read_claude(opener):
    try:
        acct = _keychain_account()
        cred = _keychain_read(acct)
        oauth = cred.get("claudeAiOauth")
        if not oauth:
            return {"ok": False, "error": "凭证格式异常"}
        # 过期（或 60s 内将过期）则刷新并写回
        if (oauth.get("expiresAt", 0) / 1000.0) <= time.time() + 60:
            data = _refresh(opener, oauth["refreshToken"])
            if "access_token" not in data:
                return {"ok": False, "error": "刷新失败"}
            oauth["accessToken"] = data["access_token"]
            oauth["refreshToken"] = data.get("refresh_token", oauth["refreshToken"])
            oauth["expiresAt"] = int((time.time() + data.get("expires_in", 3600)) * 1000)
            cred["claudeAiOauth"] = oauth
            _keychain_write(acct, cred)
        # 调 /usage
        req = urllib.request.Request(USAGE_URL, headers={
            "Authorization": "Bearer %s" % oauth["accessToken"],
            "anthropic-beta": OAUTH_BETA,
            "User-Agent": "ai-usage-agent/1.0"})
        usage = _open_json(opener, req)
        return {"ok": True,
                "plan": oauth.get("subscriptionType"),
                "five_hour": _claude_win(usage.get("five_hour")),
                "seven_day": _claude_win(usage.get("seven_day"))}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "接口 HTTP %s" % e.code}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}

def _claude_win(w):
    # Claude 是实时接口，resets_at 始终是当前窗口（未来），无需过点归零。
    if not isinstance(w, dict):
        return None
    return {"percent": round(w.get("utilization") or 0),
            "resets_at": iso_to_unix(w.get("resets_at"))}

# ------------------------------------------------- Token 统计与成本估算

STATS_CACHE = os.path.expanduser("~/.config/ai-usage-widget/token-cache.json")

# Claude 各模型单价（USD / 1M tokens）：(未缓存输入, 缓存写(1.25x), 缓存读(0.1x), 输出)
CLAUDE_PRICES = {
    "opus":   (5.0, 6.25, 0.5, 25.0),
    "sonnet": (3.0, 3.75, 0.3, 15.0),
    "haiku":  (1.0, 1.25, 0.1, 5.0),
    "fable":  (10.0, 12.5, 1.0, 50.0),
    "mythos": (10.0, 12.5, 1.0, 50.0),
}
# Codex 单价（OpenAI 官方牌价 2026-07 校准）：(未缓存输入, 缓存读, 输出)
# 按最长匹配：模型名包含 key 即用该价；找不到用 "" 默认档
CODEX_PRICES = {
    "gpt-5.6-terra": (2.5, 0.25, 15.0),
    "gpt-5.6-luna": (1.0, 0.1, 6.0),
    "gpt-5.6": (5.0, 0.5, 30.0),   # sol 与裸 5.6 同价
    "gpt-5.5": (5.0, 0.5, 30.0),
    "codex": (1.75, 0.175, 14.0),  # gpt-5.x-codex 系
    "": (5.0, 0.5, 30.0),
}

# 套餐月费（USD），用于「羊毛进度」
CLAUDE_SUB_PRICE = {"pro": 20, "max": 100, "max_5x": 100, "max_20x": 200, "team": 30}
CODEX_SUB_PRICE = {"plus": 20, "pro": 200, "business": 25, "team": 25}


def _local_date(iso):
    u = iso_to_unix(iso)
    if u is None:
        return None
    t = time.localtime(u)
    return "%04d-%02d-%02d" % (t.tm_year, t.tm_mon, t.tm_mday)


def _claude_file_msgs(path):
    """Claude Code session 文件 → {message_id: [日期, tokens, cost]}。

    同一条消息会被写成多行（流式分块）、还会被复制进续接/compact 的新文件，
    直接累加会虚高 ~60%。这里按 message.id 收敛（同 id 取 tokens 最大的一条
    ≈ 最终态），跨文件去重在合并阶段做。跳过 synthetic 合成消息。
    """
    msgs = {}
    n = 0
    with open(path, errors="ignore") as fh:
        for line in fh:
            if '"usage"' not in line or '"assistant"' not in line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("type") != "assistant":
                continue
            msg = o.get("message") or {}
            u = msg.get("usage")
            if not isinstance(u, dict):
                continue
            model = (msg.get("model") or "").lower()
            if "synthetic" in model:
                continue
            d = _local_date(o.get("timestamp") or "")
            if not d:
                continue
            unc = u.get("input_tokens") or 0
            cw = u.get("cache_creation_input_tokens") or 0
            cr = u.get("cache_read_input_tokens") or 0
            out = u.get("output_tokens") or 0
            p = next((v for k, v in CLAUDE_PRICES.items() if k in model),
                     CLAUDE_PRICES["opus"])
            cost = (unc * p[0] + cw * p[1] + cr * p[2] + out * p[3]) / 1e6
            tokens = unc + cw + cr + out
            n += 1
            mid = msg.get("id") or "~%s:%d" % (os.path.basename(path), n)
            cur = msgs.get(mid)
            if cur is None or tokens > cur[1]:
                msgs[mid] = [d, tokens, cost]
    return msgs


def _codex_file_days(path):
    """Codex session 文件 → {日期: [tokens, cost]}。

    total_token_usage 是会话内累计值，用相邻两条的差值归属到事件日期，
    对重复/缺失事件都稳健（cached_input_tokens 是 input_tokens 的子集）。
    模型跟随 turn_context 变化，按当时模型计价。
    """
    days = {}
    prev = None
    price = CODEX_PRICES[""]
    with open(path, errors="ignore") as fh:
        for line in fh:
            has_usage = "total_token_usage" in line
            if not has_usage and '"turn_context"' not in line and '"model"' not in line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            p = o.get("payload") or {}
            model = p.get("model") if isinstance(p.get("model"), str) else \
                (p.get("turn_context") or {}).get("model") if isinstance(p.get("turn_context"), dict) else None
            if isinstance(model, str):
                m = model.lower()
                price = next((v for k, v in sorted(CODEX_PRICES.items(),
                             key=lambda kv: -len(kv[0])) if k and k in m),
                             CODEX_PRICES[""])
            if not has_usage:
                continue
            info = p.get("info") or {}
            tot = info.get("total_token_usage")
            if not isinstance(tot, dict):
                continue
            cur = (tot.get("input_tokens") or 0,
                   tot.get("cached_input_tokens") or 0,
                   tot.get("output_tokens") or 0)
            if prev is None:
                d_in, d_cached, d_out = cur
            else:
                d_in = max(0, cur[0] - prev[0])
                d_cached = max(0, cur[1] - prev[1])
                d_out = max(0, cur[2] - prev[2])
            prev = cur
            if d_in == 0 and d_out == 0:
                continue
            d = _local_date(o.get("timestamp") or "")
            if not d:
                continue
            unc = max(0, d_in - d_cached)
            cost = (unc * price[0] + d_cached * price[1]
                    + d_out * price[2]) / 1e6
            rec = days.setdefault(d, [0, 0.0])
            rec[0] += d_in + d_out
            rec[1] += cost
    return days


def _scan_files(product, pattern, parser, cache):
    """按文件 (mtime,size) 增量扫描；未变的文件直接用缓存结果。"""
    old = cache.get(product) or {}
    live = {}
    for path in glob.glob(os.path.expanduser(pattern), recursive=True):
        try:
            st = os.stat(path)
        except OSError:
            continue
        sig = [int(st.st_mtime), st.st_size]
        rec = old.get(path)
        if rec and rec.get("sig") == sig:
            live[path] = rec
        else:
            try:
                live[path] = {"sig": sig, "data": parser(path)}
            except Exception:
                continue
    cache[product] = live
    return live


def _claude_days(cache):
    """跨文件按 message_id 全局去重后聚合成 {日期: [tokens, cost]}。"""
    live = _scan_files("claude", "~/.claude/projects/**/*.jsonl",
                       _claude_file_msgs, cache)
    best = {}
    for rec in live.values():
        for mid, v in rec["data"].items():
            cur = best.get(mid)
            if cur is None or v[1] > cur[1]:
                best[mid] = v
    days = {}
    for v in best.values():
        m = days.setdefault(v[0], [0, 0.0])
        m[0] += v[1]
        m[1] += v[2]
    return days


def _codex_days(cache):
    live = _scan_files("codex", "~/.codex/sessions/**/*.jsonl",
                       _codex_file_days, cache)
    days = {}
    for rec in live.values():
        for d, v in rec["data"].items():
            m = days.setdefault(d, [0, 0.0])
            m[0] += v[0]
            m[1] += v[1]
    return days


def _buckets(days):
    now = time.localtime()
    today = "%04d-%02d-%02d" % (now.tm_year, now.tm_mon, now.tm_mday)
    wk = time.localtime(time.time() - 6 * 86400)
    week_from = "%04d-%02d-%02d" % (wk.tm_year, wk.tm_mon, wk.tm_mday)
    month = today[:7]
    b = {"today": [0, 0.0], "week": [0, 0.0], "total": [0, 0.0]}
    month_cost = 0.0
    for d, v in days.items():
        b["total"][0] += v[0]
        b["total"][1] += v[1]
        if d >= week_from:
            b["week"][0] += v[0]
            b["week"][1] += v[1]
        if d == today:
            b["today"][0] += v[0]
            b["today"][1] += v[1]
        if d[:7] == month:
            month_cost += v[1]
    return {k: {"tokens": v[0], "cost": round(v[1], 2)} for k, v in b.items()} | \
           {"month_cost": round(month_cost, 2)}


STATS = {"data": None, "ts": 0}


CACHE_VER = 2   # 结构变更时递增，旧缓存自动作废重算

def compute_stats():
    try:
        with open(STATS_CACHE) as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    if cache.get("ver") != CACHE_VER:
        cache = {"ver": CACHE_VER}
    claude = _buckets(_claude_days(cache))
    codex = _buckets(_codex_days(cache))
    try:
        os.makedirs(os.path.dirname(STATS_CACHE), exist_ok=True)
        with open(STATS_CACHE, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass
    return {"claude": claude, "codex": codex}


def stats_loop():
    while True:
        try:
            STATS["data"] = compute_stats()
            STATS["ts"] = time.time()
        except Exception as e:
            sys.stderr.write("token 统计失败: %r\n" % e)
        time.sleep(300)

# ---------------------------------------------------------------- 合并 + 缓存

LAST_GOOD_PATH = os.path.expanduser("~/.config/ai-usage-widget/last-good.json")

class Snapshot:
    def __init__(self, cache_seconds):
        self.cache_seconds = cache_seconds
        self.payload = None
        self.ts = 0
        # 上次成功值落盘，重启/429/断网时兜底展示（略旧胜过报错）
        self.last_good = self._load()

    def _load(self):
        try:
            with open(LAST_GOOD_PATH) as f:
                d = json.load(f)
            return {"claude": d.get("claude"), "codex": d.get("codex")}
        except Exception:
            return {"claude": None, "codex": None}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(LAST_GOOD_PATH), exist_ok=True)
            with open(LAST_GOOD_PATH, "w") as f:
                json.dump(self.last_good, f)
        except Exception:
            pass

    def get(self, opener):
        now = time.time()
        if self.payload and now - self.ts < self.cache_seconds:
            return self.payload
        claude = read_claude(opener)
        codex = read_codex(opener)
        # 取数失败（429/断网/未登录）时复用上次成功值，避免卡片报错/闪空
        changed = False
        for key, val in (("claude", claude), ("codex", codex)):
            if val.get("ok"):
                self.last_good[key] = val
                changed = True
            elif self.last_good[key]:
                val = dict(self.last_good[key])
                val["stale"] = True
                if key == "claude":
                    claude = val
                else:
                    codex = val
        if changed:
            self._save()
        self.payload = {"updated": int(now), "claude": claude, "codex": codex}
        self.ts = now
        return self.payload

# ---------------------------------------------------------------- UI 偏好

UI_CONFIG = os.path.expanduser("~/.config/ai-usage-widget/ui.json")

def read_theme():
    try:
        return json.load(open(UI_CONFIG)).get("theme", "system")
    except Exception:
        return "system"

def write_theme(t):
    if t not in ("system", "light", "dark"):
        return
    os.makedirs(os.path.dirname(UI_CONFIG), exist_ok=True)
    data = {}
    try:
        data = json.load(open(UI_CONFIG))
    except Exception:
        pass
    data["theme"] = t
    with open(UI_CONFIG, "w") as f:
        json.dump(data, f)

# ---------------------------------------------------------------- HTTP

def serve(cfg):
    opener = make_opener(cfg.get("proxy"))
    snap = Snapshot(cfg.get("cache_seconds", 60))

    class Handler(BaseHTTPRequestHandler):
        def _json(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/")
            if path == "/config":
                q = urllib.parse.parse_qs(parsed.query)
                if "theme" in q:
                    write_theme(q["theme"][0])
                self._json({"ok": True, "theme": read_theme()})
                return
            if path in ("/usage", ""):
                try:
                    payload = dict(snap.get(opener))
                    payload["theme"] = read_theme()   # 不进缓存，改了立即生效
                    payload["stats"] = _stats_payload(payload)
                    self._json(payload)
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(str(e).encode())
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):
            pass

    port = int(cfg.get("port", 47615))
    threading.Thread(target=stats_loop, daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    sys.stderr.write("ai-usage-agent 监听 http://127.0.0.1:%d/usage\n" % port)
    httpd.serve_forever()


def _stats_payload(payload):
    """附上套餐月费，供前端算「羊毛倍数」；stats 未就绪时返回 None。"""
    data = STATS["data"]
    if not data:
        return None
    out = {k: dict(v) for k, v in data.items()}
    plan_c = ((payload.get("claude") or {}).get("plan") or "").lower()
    plan_x = ((payload.get("codex") or {}).get("plan") or "").lower()
    out["claude"]["sub_price"] = CLAUDE_SUB_PRICE.get(plan_c)
    out["codex"]["sub_price"] = CODEX_SUB_PRICE.get(plan_x)
    return out

# ---------------------------------------------------------------- main

def main():
    cfg = load_config()
    if "--once" in sys.argv:
        opener = make_opener(cfg.get("proxy"))
        STATS["data"] = compute_stats()
        payload = {"updated": int(time.time()),
                   "claude": read_claude(opener),
                   "codex": read_codex(opener),
                   "theme": read_theme()}
        payload["stats"] = _stats_payload(payload)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    serve(cfg)

if __name__ == "__main__":
    main()
