"""缓存兜底必须保留原始失败阶段和响应详情。"""
import importlib.util
import pathlib
import sys

AGENT = str(pathlib.Path(__file__).resolve().parent.parent / "usage-agent.py")
spec = importlib.util.spec_from_file_location("agent", AGENT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

m.read_claude = lambda opener: {
    "ok": False,
    "error": "登录已失效，请重新登录",
    "relogin": True,
    "stage": "refresh",
    "detail": "Refresh token not found or invalid",
}
m.read_codex = lambda opener: {
    "ok": True,
    "plan": "plus",
    "five_hour": None,
    "seven_day": None,
}

snapshot = m.Snapshot(cache_seconds=0)
snapshot.last_good = {
    "claude": {
        "ok": True,
        "plan": "pro",
        "five_hour": None,
        "seven_day": None,
    },
    "codex": None,
}
snapshot._save = lambda: None

claude = snapshot._fetch(None)["claude"]
expected = {
    "stale": True,
    "error": "登录已失效，请重新登录",
    "relogin": True,
    "stage": "refresh",
    "detail": "Refresh token not found or invalid",
}
failures = [
    "%s=%r，应为 %r" % (key, claude.get(key), value)
    for key, value in expected.items()
    if claude.get(key) != value
]

if failures:
    print("❌ stale 失败元数据丢失：")
    for failure in failures:
        print("  -", failure)
    sys.exit(1)

print("✅ stale payload 保留了 error/relogin/stage/detail")
