"""自愈测试：Keychain 里的 refreshToken 已被 claude 自己轮换作废时，
agent 应重读 Keychain 捡起新 token，而不是直接报「请重新登录」。"""
import importlib.util, json, urllib.error, io, sys, pathlib

AGENT = str(pathlib.Path(__file__).resolve().parent.parent / "usage-agent.py")
spec = importlib.util.spec_from_file_location("agent", AGENT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

state = {"reads": 0}
# 第一次读到的是已作废的 rt-dead；claude 随后写回了 rt-live
def fake_read(acct):
    state["reads"] += 1
    rt = "rt-dead" if state["reads"] == 1 else "rt-live"
    return {"claudeAiOauth": {"accessToken": "at-old", "refreshToken": rt,
                              "expiresAt": 0, "subscriptionType": "pro"}}

def fake_refresh(opener, refresh_token):
    if refresh_token == "rt-dead":
        raise urllib.error.HTTPError(
            m.TOKEN_URL, 400, "Bad Request", {},
            io.BytesIO(json.dumps({"error": "invalid_grant",
                                   "error_description": "Refresh token not found or invalid"}).encode()))
    return {"access_token": "at-new", "refresh_token": "rt-next", "expires_in": 3600}

m._keychain_account = lambda: "tester"
m._keychain_read = fake_read
m._keychain_write = lambda acct, cred: None
m._refresh = fake_refresh
m._open_json = lambda opener, req, attempts=3: {
    "five_hour": {"utilization": 36, "resets_at": None},
    "seven_day": {"utilization": 24, "resets_at": None}}

r = m.read_claude(None)
print("结果:", json.dumps(r, ensure_ascii=False))
if not r.get("ok"):
    print("\n❌ 失败：没有自愈，仍然要求重新登录")
    sys.exit(1)
print("\n✅ 通过：捡起了 claude 写回的新 token，无需重新登录")

# 反向用例：Keychain 里始终是死 token → 必须报「需重新登录」
state["reads"] = 99
m._keychain_read = lambda acct: {"claudeAiOauth": {
    "accessToken": "at-old", "refreshToken": "rt-dead", "expiresAt": 0, "subscriptionType": "pro"}}
r2 = m.read_claude(None)
print("\n死 token 用例:", json.dumps(r2, ensure_ascii=False))
if (r2.get("ok") or not r2.get("relogin")
        or r2.get("stage") != "refresh"
        or r2.get("detail") != "Refresh token not found or invalid"):
    print("❌ 失败：真的失效时应标记 relogin，并保留 refresh 阶段与响应详情")
    sys.exit(1)
print("✅ 通过：真失效时正确标记 relogin")

# 登出用例：条目里只剩 mcpOAuth、没有 claudeAiOauth → 也必须报「需重新登录」
m._keychain_read = lambda acct: {"mcpOAuth": {}}
r3 = m.read_claude(None)
print("\n已登出用例:", json.dumps(r3, ensure_ascii=False))
if r3.get("ok") or not r3.get("relogin"):
    print("❌ 失败：CLI 登出时应标记 relogin")
    sys.exit(1)
print("✅ 通过：CLI 登出时正确标记 relogin")
