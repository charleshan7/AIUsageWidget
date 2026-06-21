#!/usr/bin/env python3
"""生成 AppIcon 与菜单栏图标。
图标语义：两道横向进度条 = Claude / Codex 两个工具的用量。
依赖：Pillow。运行：python3 make_icons.py
"""
import os
import json
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(ROOT, "App", "Assets.xcassets")
APPICON = os.path.join(ASSETS, "AppIcon.appiconset")
MENUBAR = os.path.join(ASSETS, "MenuBarIcon.imageset")
for d in (ASSETS, APPICON, MENUBAR):
    os.makedirs(d, exist_ok=True)

GRAPHITE = (31, 33, 40, 255)
TRACK = (58, 61, 71, 255)
CORAL = (208, 138, 111, 255)
TEAL = (95, 160, 140, 255)


def app_icon(base: int) -> Image.Image:
    img = Image.new("RGBA", (base, base), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    margin = round(base * 0.085)
    side = base - 2 * margin
    radius = round(side * 0.2237)
    d.rounded_rectangle([margin, margin, base - margin - 1, base - margin - 1],
                        radius=radius, fill=GRAPHITE)
    inset = round(side * 0.20)
    x0 = margin + inset
    x1 = base - margin - inset
    inner_w = x1 - x0
    bar_h = round(side * 0.135)
    gap = round(side * 0.11)
    total = bar_h * 2 + gap
    y0 = (base - total) // 2

    def bar(y, frac, color):
        r = bar_h // 2
        d.rounded_rectangle([x0, y, x1, y + bar_h], radius=r, fill=TRACK)
        w = max(bar_h, round(inner_w * frac))
        d.rounded_rectangle([x0, y, x0 + w, y + bar_h], radius=r, fill=color)

    bar(y0, 0.60, CORAL)
    bar(y0 + bar_h + gap, 0.36, TEAL)
    return img


def menubar(base: int) -> Image.Image:
    """单色模板图（黑色 + alpha），macOS 自动黑/白适配。"""
    img = Image.new("RGBA", (base, base), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bar_h = max(2, round(base * 0.135))
    gap = round(base * 0.17)
    total = bar_h * 2 + gap
    y0 = (base - total) // 2
    x0 = round(base * 0.14)
    w_full = base - 2 * x0
    r = bar_h // 2
    black = (0, 0, 0, 255)
    d.rounded_rectangle([x0, y0, x0 + w_full, y0 + bar_h], radius=r, fill=black)
    d.rounded_rectangle([x0, y0 + bar_h + gap, x0 + round(w_full * 0.62),
                         y0 + bar_h + gap + bar_h], radius=r, fill=black)
    return img


# ---- AppIcon ----
for s in [16, 32, 64, 128, 256, 512, 1024]:
    app_icon(s).save(os.path.join(APPICON, f"icon_{s}.png"))

appicon_contents = {
    "images": [
        {"idiom": "mac", "scale": "1x", "size": "16x16", "filename": "icon_16.png"},
        {"idiom": "mac", "scale": "2x", "size": "16x16", "filename": "icon_32.png"},
        {"idiom": "mac", "scale": "1x", "size": "32x32", "filename": "icon_32.png"},
        {"idiom": "mac", "scale": "2x", "size": "32x32", "filename": "icon_64.png"},
        {"idiom": "mac", "scale": "1x", "size": "128x128", "filename": "icon_128.png"},
        {"idiom": "mac", "scale": "2x", "size": "128x128", "filename": "icon_256.png"},
        {"idiom": "mac", "scale": "1x", "size": "256x256", "filename": "icon_256.png"},
        {"idiom": "mac", "scale": "2x", "size": "256x256", "filename": "icon_512.png"},
        {"idiom": "mac", "scale": "1x", "size": "512x512", "filename": "icon_512.png"},
        {"idiom": "mac", "scale": "2x", "size": "512x512", "filename": "icon_1024.png"},
    ],
    "info": {"author": "xcode", "version": 1},
}
with open(os.path.join(APPICON, "Contents.json"), "w") as f:
    json.dump(appicon_contents, f, indent=2)

# ---- 菜单栏图标（模板）----
menubar(18).save(os.path.join(MENUBAR, "menubar.png"))
menubar(36).save(os.path.join(MENUBAR, "menubar@2x.png"))
menubar_contents = {
    "images": [
        {"idiom": "mac", "scale": "1x", "filename": "menubar.png"},
        {"idiom": "mac", "scale": "2x", "filename": "menubar@2x.png"},
    ],
    "info": {"author": "xcode", "version": 1},
    "properties": {"template-rendering-intent": "template"},
}
with open(os.path.join(MENUBAR, "Contents.json"), "w") as f:
    json.dump(menubar_contents, f, indent=2)

# ---- 资产目录根 ----
with open(os.path.join(ASSETS, "Contents.json"), "w") as f:
    json.dump({"info": {"author": "xcode", "version": 1}}, f, indent=2)

print("✅ 图标已生成：AppIcon.appiconset + MenuBarIcon.imageset")
