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
import getpass
import subprocess
import datetime
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEYCHAIN_SERVICE = "Claude Code-credentials"
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
TOKEN_URL = "https://api.anthropic.com/v1/oauth/token"
OAUTH_BETA = "oauth-2025-04-20"

DEFAULTS = {"port": 47615, "proxy": "http://127.0.0.1:7897", "cache_seconds": 60}

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

def read_codex():
    """从最新的 Codex session 文件读取最后一条 rate_limits。"""
    pattern = os.path.expanduser("~/.codex/sessions/**/*.jsonl")
    files = sorted(glob.glob(pattern, recursive=True), key=os.path.getmtime, reverse=True)
    for path in files[:40]:
        last = None
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
                    if isinstance(rl, dict):
                        last = rl
        except Exception:
            continue
        if last:
            return _codex_payload(last)
    return {"ok": False, "error": "无数据（还没用过 Codex？）"}

def _codex_payload(rl):
    def win(w):
        if not isinstance(w, dict):
            return None
        return {"percent": round(w.get("used_percent") or 0),
                "resets_at": int(w["resets_at"]) if w.get("resets_at") else None}
    return {"ok": True,
            "five_hour": win(rl.get("primary")),
            "seven_day": win(rl.get("secondary"))}

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

def _refresh(opener, refresh_token):
    body = json.dumps({"grant_type": "refresh_token",
                       "refresh_token": refresh_token,
                       "client_id": OAUTH_CLIENT_ID}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "ai-usage-agent/1.0"})
    with opener.open(req, timeout=25) as r:
        return json.loads(r.read().decode())

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
        with opener.open(req, timeout=25) as r:
            usage = json.loads(r.read().decode())
        return {"ok": True,
                "plan": oauth.get("subscriptionType"),
                "five_hour": _claude_win(usage.get("five_hour")),
                "seven_day": _claude_win(usage.get("seven_day"))}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "接口 HTTP %s" % e.code}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}

def _claude_win(w):
    if not isinstance(w, dict):
        return None
    return {"percent": round(w.get("utilization") or 0),
            "resets_at": iso_to_unix(w.get("resets_at"))}

# ---------------------------------------------------------------- 合并 + 缓存

class Snapshot:
    def __init__(self, cache_seconds):
        self.cache_seconds = cache_seconds
        self.payload = None
        self.ts = 0
        self.last_good = {"claude": None, "codex": None}

    def get(self, opener):
        now = time.time()
        if self.payload and now - self.ts < self.cache_seconds:
            return self.payload
        claude = read_claude(opener)
        codex = read_codex()
        # 取数失败时复用上次成功值，避免卡片闪空
        for key, val in (("claude", claude), ("codex", codex)):
            if val.get("ok"):
                self.last_good[key] = val
            elif self.last_good[key]:
                val = dict(self.last_good[key])
                val["stale"] = True
                if key == "claude":
                    claude = val
                else:
                    codex = val
        self.payload = {"updated": int(now), "claude": claude, "codex": codex}
        self.ts = now
        return self.payload

# ---------------------------------------------------------------- HTTP

def serve(cfg):
    opener = make_opener(cfg.get("proxy"))
    snap = Snapshot(cfg.get("cache_seconds", 60))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.rstrip("/") not in ("/usage", ""):
                self.send_response(404)
                self.end_headers()
                return
            try:
                body = json.dumps(snap.get(opener)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())

        def log_message(self, *args):
            pass

    port = int(cfg.get("port", 47615))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    sys.stderr.write("ai-usage-agent 监听 http://127.0.0.1:%d/usage\n" % port)
    httpd.serve_forever()

# ---------------------------------------------------------------- main

def main():
    cfg = load_config()
    if "--once" in sys.argv:
        opener = make_opener(cfg.get("proxy"))
        print(json.dumps({"updated": int(time.time()),
                          "claude": read_claude(opener),
                          "codex": read_codex()}, indent=2, ensure_ascii=False))
        return
    serve(cfg)

if __name__ == "__main__":
    main()
