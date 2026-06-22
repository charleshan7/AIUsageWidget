#!/usr/bin/env python3
"""生成 README 用的宣传图（浅色三卡 + 品牌标题，柔和渐变背景）。
依赖 Pillow + 系统字体 Hiragino Sans GB。运行：python3 make_hero.py
"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SS = 2  # 超采样，最后缩小一半得到清晰边缘
def s(v): return int(v * SS)

FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
def reg(size): return ImageFont.truetype(FONT, s(size), index=0)   # W3
def med(size): return ImageFont.truetype(FONT, s(size), index=1)   # W6

CARD = (252, 252, 251)
TEXT = (38, 38, 43)
SEC = (118, 121, 128)
TER = (164, 167, 177)
TRACK = (231, 231, 236)
CLAUDE = (199, 133, 112)
CODEX = (107, 163, 145)
GREEN = (117, 168, 125)
AMBER = (217, 168, 92)
RED = (204, 115, 107)
PILL = (231, 231, 236)

def sev(p): return RED if p >= 80 else (AMBER if p >= 50 else GREEN)

W, H = 1480, 1030
canvas = Image.new("RGBA", (s(W), s(H)), (0, 0, 0, 0))

# ---- 背景渐变 ----
top, bot = (214, 228, 242), (239, 233, 221)
grad = Image.new("RGB", (1, s(H)))
for y in range(s(H)):
    t = y / s(H)
    grad.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
canvas.paste(grad.resize((s(W), s(H))), (0, 0))

draw = ImageDraw.Draw(canvas)

def card(box, radius=28):
    x0, y0, x1, y1 = [s(v) for v in box]
    r = s(radius)
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ds = ImageDraw.Draw(shadow)
    ds.rounded_rectangle([x0, y0 + s(10), x1, y1 + s(14)], radius=r, fill=(40, 55, 80, 60))
    shadow = shadow.filter(ImageFilter.GaussianBlur(s(16)))
    canvas.alpha_composite(shadow)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=CARD)

def bar(x, y, w, h, frac, color):
    x, y, w, h = s(x), s(y), s(w), s(h)
    rr = h // 2
    draw.rounded_rectangle([x, y, x + w, y + h], radius=rr, fill=TRACK)
    fw = max(h, int(w * frac))
    draw.rounded_rectangle([x, y, x + fw, y + h], radius=rr, fill=color)

def header(x, y, dot, name, plan, name_size=15, dot_r=4):
    cy = s(y)
    dr = s(dot_r)
    draw.ellipse([s(x), cy - dr, s(x) + 2 * dr, cy + dr], fill=dot)
    nx = s(x) + 2 * dr + s(7)
    f = med(name_size)
    draw.text((nx, cy), name, font=f, fill=TEXT, anchor="lm")
    if plan:
        nw = draw.textlength(name, font=f)
        px0 = nx + nw + s(8)
        pf = reg(11)
        pw = draw.textlength(plan, font=pf)
        pad = s(6)
        ph = s(9)
        draw.rounded_rectangle([px0, cy - ph, px0 + pw + 2 * pad, cy + ph],
                               radius=ph, fill=PILL)
        draw.text((px0 + pad, cy), plan, font=pf, fill=SEC, anchor="lm")

def refresh_icon(x, y, r=11):
    cx, cy, rr = s(x), s(y), s(r)
    draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=TRACK)
    draw.arc([cx - s(5), cy - s(5), cx + s(5), cy + s(5)], 30, 300, fill=SEC, width=s(2))

# ============ 标题区（左上）============
ICON = (31, 33, 40)
ix, iy, isz = 70, 110, 104
draw.rounded_rectangle([s(ix), s(iy), s(ix + isz), s(iy + isz)], radius=s(24), fill=ICON)
bx0, bx1 = ix + 22, ix + isz - 22
bw = bx1 - bx0
bar(bx0, iy + 34, bw, 13, 0.60, CLAUDE)
bar(bx0, iy + 58, bw, 13, 0.36, CODEX)
draw.text((s(ix + isz + 26), s(iy + 30)), "AI 用量小组件", font=med(36), fill=(33, 40, 55), anchor="lm")
draw.text((s(ix + isz + 26), s(iy + 74)), "Claude Code · Codex 用量，一眼看尽",
          font=reg(18), fill=(70, 84, 105), anchor="lm")

# ============ 中卡（右上）============
mx0, my0, mx1 = 800, 70, 1400
card([mx0, my0, mx1, 380])
refresh_icon(mx1 - 36, my0 + 36)
colw = (mx1 - mx0 - 60) // 2
# Claude 列
cx = mx0 + 28
header(cx, my0 + 40, CLAUDE, "Claude Co...", "Pro", name_size=15)
def medium_metric(x, y, w, label, pct, reset):
    draw.text((s(x), s(y)), label, font=reg(12), fill=SEC, anchor="lm")
    draw.text((s(x + w), s(y)), f"{pct}%", font=med(13), fill=TEXT, anchor="rm")
    bar(x, y + 9, w, 6, pct / 100, sev(pct))
    draw.text((s(x), s(y + 26)), reset, font=reg(10.5), fill=TER, anchor="lm")
medium_metric(cx, my0 + 78, colw, "5 小时", 19, "约 4 小时后重置")
medium_metric(cx, my0 + 130, colw, "一周", 50, "5 天后重置")
# 分隔线
draw.line([s(mx0 + colw + 44), s(my0 + 30), s(mx0 + colw + 44), s(380 - 30)], fill=TRACK, width=s(1))
# Codex 列
cx2 = mx0 + colw + 60
header(cx2, my0 + 40, CODEX, "Codex", "Plus", name_size=15)
medium_metric(cx2, my0 + 78, colw, "5 小时", 1, "约 2 小时后重置")
medium_metric(cx2, my0 + 130, colw, "一周", 49, "6 天后重置")

# ============ 小卡（左中）============
sx0, sy0, sx1, sy1 = 70, 410, 390, 730
card([sx0, sy0, sx1, sy1])
refresh_icon(sx1 - 32, sy0 + 34, r=10)
def small_block(x, y, dot, name, plan, m5, mw):
    header(x, y, dot, name, plan, name_size=14)
    def row(yy, label, pct):
        draw.text((s(x), s(yy)), label, font=reg(11), fill=SEC, anchor="lm")
        bar(x + 26, yy - 3, 150, 5, pct / 100, sev(pct))
        draw.text((s(x + 250), s(yy)), f"{pct}%", font=med(12), fill=TEXT, anchor="rm")
    row(y + 30, "5h", m5)
    row(y + 56, "周", mw)
small_block(sx0 + 24, sy0 + 36, CLAUDE, "Claude", "Pro", 19, 50)
small_block(sx0 + 24, sy0 + 150, CODEX, "Codex", "Plus", 1, 49)

# ============ 大卡（右下）============
lx0, ly0, lx1, ly1 = 800, 410, 1400, 965
card([lx0, ly0, lx1, ly1])
refresh_icon(lx1 - 40, ly0 + 40)
lw = lx1 - lx0 - 64
def large_metric(x, y, w, label, pct, reset):
    draw.text((s(x), s(y)), label, font=reg(13.5), fill=SEC, anchor="lm")
    draw.text((s(x + w), s(y)), f"{pct}%", font=med(15), fill=TEXT, anchor="rm")
    bar(x, y + 12, w, 8, pct / 100, sev(pct))
    draw.text((s(x), s(y + 34)), reset, font=reg(12), fill=TER, anchor="lm")
lcx = lx0 + 32
header(lcx, ly0 + 48, CLAUDE, "Claude Code", "Pro", name_size=17, dot_r=5)
large_metric(lcx, ly0 + 96, lw, "5 小时窗口", 19, "约 4 小时后重置 · 今天 21:40")
large_metric(lcx, ly0 + 160, lw, "一周窗口", 50, "5 天后重置 · 6/27 18:00")
draw.line([s(lcx), s(ly0 + 230), s(lx1 - 32), s(ly0 + 230)], fill=TRACK, width=s(1))
header(lcx, ly0 + 280, CODEX, "Codex", "Plus", name_size=17, dot_r=5)
large_metric(lcx, ly0 + 328, lw, "5 小时窗口", 1, "约 2 小时后重置 · 今天 19:00")
large_metric(lcx, ly0 + 392, lw, "一周窗口", 49, "6 天后重置 · 6/28 08:44")

# ---- 输出 ----
out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "images")
os.makedirs(out_dir, exist_ok=True)
final = canvas.convert("RGB").resize((W, H), Image.LANCZOS)
out = os.path.join(out_dir, "hero.png")
final.save(out)
print("✅", out)
