"""并发刷新竞态回归测试：模拟 refreshToken 轮换的服务端语义。

服务端规则：只认当前 refreshToken，一旦被消费即轮换成新的，旧的立刻作废。
若 agent 并发刷新，第二个线程会拿着已作废的 token 去刷 → 400，
或两次都成功但写回顺序颠倒 → Keychain 留下已作废的 token（永久坏掉）。
"""
import importlib.util, threading, time, sys, json, pathlib

AGENT = str(pathlib.Path(__file__).resolve().parent.parent / "usage-agent.py")
spec = importlib.util.spec_from_file_location("agent", AGENT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# ---- 假 Keychain ----
KEYCHAIN = {"claudeAiOauth": {"accessToken": "at-0", "refreshToken": "rt-0",
                              "expiresAt": 0, "subscriptionType": "pro"}}
kc_lock = threading.Lock()

def fake_account():
    return "tester"

def fake_read(acct):
    with kc_lock:
        return json.loads(json.dumps(KEYCHAIN))   # 深拷贝，模拟真实读取

def fake_write(acct, cred):
    with kc_lock:
        KEYCHAIN.clear()
        KEYCHAIN.update(json.loads(json.dumps(cred)))

# ---- 假服务端：refreshToken 轮换 ----
server = {"valid_rt": "rt-0", "n": 0, "refresh_calls": 0, "rejected": 0}
srv_lock = threading.Lock()

def fake_refresh(opener, refresh_token):
    with srv_lock:
        server["refresh_calls"] += 1
        if refresh_token != server["valid_rt"]:
            server["rejected"] += 1
            raise RuntimeError("Refresh token not found or invalid (拿到的是已作废的 %s)" % refresh_token)
        server["n"] += 1
        new_rt = "rt-%d" % server["n"]
        server["valid_rt"] = new_rt
    time.sleep(0.05)   # 放大竞态窗口
    return {"access_token": "at-%d" % server["n"], "refresh_token": new_rt, "expires_in": 3600}

def fake_open_json(opener, req, attempts=3):
    return {"five_hour": {"utilization": 42, "resets_at": None},
            "seven_day": {"utilization": 7, "resets_at": None}}

m._keychain_account = fake_account
m._keychain_read = fake_read
m._keychain_write = fake_write
m._refresh = fake_refresh
m._open_json = fake_open_json

# ---- 8 个线程同时取数（= reloadAllTimelines 唤醒小/中/大 + 菜单栏 App）----
results = []
def worker():
    results.append(m.read_claude(None))

threads = [threading.Thread(target=worker) for _ in range(8)]
for t in threads: t.start()
for t in threads: t.join()

ok = sum(1 for r in results if r.get("ok"))
print("并发取数 8 次 → 成功 %d，刷新调用 %d 次，被服务端拒绝 %d 次"
      % (ok, server["refresh_calls"], server["rejected"]))
print("Keychain 里最终 refreshToken:", KEYCHAIN["claudeAiOauth"]["refreshToken"],
      "| 服务端当前有效:", server["valid_rt"])

fail = []
if server["refresh_calls"] != 1:
    fail.append("刷新未串行（调用了 %d 次，应为 1 次）" % server["refresh_calls"])
if KEYCHAIN["claudeAiOauth"]["refreshToken"] != server["valid_rt"]:
    fail.append("Keychain 存的 refreshToken 已作废 → 凭证永久坏掉")
if ok != 8:
    fail.append("有 %d 个请求取数失败" % (8 - ok))

if fail:
    print("\n❌ 失败：")
    for f in fail: print("  -", f)
    sys.exit(1)
print("\n✅ 通过：刷新已串行，Keychain 与服务端一致")
