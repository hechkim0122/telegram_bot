"""منطق بازی‌ها و ساخت تصویر. بدون وابستگی به تلگرام."""
import html
import io
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).parent
# مار و نردبان‌ها دقیقاً مطابق نقاشی تخته (board.jpg)
SNAKES = {97: 65, 87: 47, 72: 50, 61: 42, 34: 12}
LADDERS = {7: 26, 12: 31, 23: 44, 43: 64, 48: 67, 62: 81, 66: 85, 73: 92}
EMO = ["🦁", "🐉", "🌳", "🔥", "🐺"]  # شیر، اژدها، درخت، ققنوس، گرگ (به ترتیب مهره‌ها)
COIN = 68
HINTS = True  # نمایش خط‌چین و مقصد مار و نردبان‌ها روی تخته؛ برای خاموش کردن False بذار
LAYOUT = {
    1: [(0, 0)], 2: [(-26, 0), (26, 0)], 3: [(-26, -18), (26, -18), (0, 24)],
    4: [(-26, -22), (26, -22), (-26, 22), (26, 22)], 5: [(-26, -22), (26, -22), (-26, 22), (26, 22), (0, 0)],
}
esc = html.escape
_A = {}


def xy(n):
    r, c = divmod(n - 1, 10)
    if r % 2:
        c = 9 - c
    return 47 + 119.75 * (c + .5), 29 + 116.8 * (9 - r + .5)


def _assets():
    if not _A:
        _A["board"] = Image.open(BASE / "board.jpg").convert("RGBA")
        sheet = Image.open(BASE / "coins.png").convert("RGBA")
        h = sheet.height
        _A["coins"] = [sheet.crop((i * h, 0, (i + 1) * h, h)).resize((COIN, COIN), Image.LANCZOS) for i in range(5)]
    return _A


def _hints(im):
    """خط‌چین و برچسب مقصد روی هر مار (قرمز) و نردبان (سبز) تا معلوم باشه کجا می‌رن."""
    d = ImageDraw.Draw(im, "RGBA")
    f = ImageFont.load_default(size=24)
    items = [(a, b, (220, 38, 38), 1) for a, b in SNAKES.items()] + [(a, b, (22, 163, 74), -1) for a, b in LADDERS.items()]
    for a, b, col, dirn in items:
        (x1, y1), (x2, y2) = xy(a), xy(b)
        n = max(int(math.hypot(x2 - x1, y2 - y1) / 24), 2)
        for i in range(0, n, 2):
            t0, t1 = i / n, min((i + 1) / n, 1)
            d.line([(x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0), (x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1)],
                   fill=col + (200,), width=7)
        d.ellipse([x2 - 12, y2 - 12, x2 + 12, y2 + 12], fill=(255, 255, 255, 235), outline=col + (255,), width=5)
        t = str(b)
        w = d.textlength(t, font=f)
        cx, cy = x1, y1 + 40
        d.rounded_rectangle([cx - w / 2 - 30, cy - 17, cx + w / 2 + 14, cy + 17], 14, fill=col + (235,), outline="white", width=2)
        ax = cx - w / 2 - 15
        tri = [(ax - 8, cy - 7 * dirn), (ax + 8, cy - 7 * dirn), (ax, cy + 8 * dirn)]
        d.polygon(tri, fill="white")
        d.text((cx - w / 2 + 2, cy - 14), t, fill="white", font=f)


def render_board(pos, turn=None):
    A = _assets()
    im = A["board"].copy()
    if HINTS:
        _hints(im)
    groups = {}
    for i, p in enumerate(pos):
        groups.setdefault(max(p, 1), []).append(i)
    for cell, ids in groups.items():
        cx, cy = xy(cell)
        for k, i in enumerate(ids):
            ox, oy = LAYOUT[len(ids)][k]
            x, y = int(cx + ox - COIN / 2), int(cy + oy - COIN / 2)
            sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
            ImageDraw.Draw(sh).ellipse([x + 3, y + 8, x + COIN + 3, y + COIN + 8], fill=(0, 0, 0, 110))
            im = Image.alpha_composite(im, sh)
            im.alpha_composite(A["coins"][i], (x, y))
            if turn is not None and i == turn:  # حلقه‌ی روشن دور مهره‌ی نوبت فعلی
                ImageDraw.Draw(im, "RGBA").ellipse([x - 6, y - 6, x + COIN + 6, y + COIN + 6], outline=(255, 255, 255, 255), width=6)
    buf = io.BytesIO()
    im.convert("RGB").resize((1000, 1000), Image.LANCZOS).save(buf, "JPEG", quality=88)
    return buf.getvalue()


# ---------- مارپله ----------
def sn_new():
    return {"players": [], "started": False, "pos": [], "T": 0, "msg": "", "win": -1}


def sn_roll(g):
    T = g["T"]
    name = g["players"][T][1]
    d = random.randint(1, 6)
    p = g["pos"][T]
    t = p + d
    note = f"🎲 {d}"
    if t > 100:
        note += " (عدد زیاده، سر جاشه)"
        t = p
    elif t in SNAKES or t in LADDERS:
        j = SNAKES.get(t) or LADDERS[t]
        note += f" ← {'🐍 مار' if t in SNAKES else '🪜 نردبان'} {t}→{j}"
        t = j
    g["pos"][T] = t
    if t == 100:
        g["win"] = T
    elif d == 6:
        note += " (۶ آورد، نوبت اضافه ✨)"
    else:
        g["T"] = (T + 1) % len(g["players"])
    g["msg"] = f"{esc(name)}: {note}"


def sn_caption(g):
    lines = ["🐍 <b>مارپله</b>"]
    if not g["players"]:
        return lines[0] + "\n\nبازیکن‌ها رو منتظریم. ۲ تا ۵ نفر بپیوندن 👇"
    for i, (_, n) in enumerate(g["players"]):
        at = f" — خونه {g['pos'][i]}" if g["started"] else ""
        lines.append(f"{EMO[i]} {esc(n)}{at}")
    if not g["started"]:
        lines.append("\nنفر اول میزبانه و بازی رو شروع می‌کنه.")
    elif g["win"] >= 0:
        lines += ["", f"🏆 <b>{esc(g['players'][g['win']][1])} برنده شد!</b>"]
    else:
        lines += ["", g["msg"], f"نوبت: {EMO[g['T']]} <b>{esc(g['players'][g['T']][1])}</b>"]
    return "\n".join(l for l in lines if l is not None)


# ---------- دوز ----------
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def xo_new():
    return {"p": [], "b": [""] * 9, "n": 0, "res": None}


def xo_result(b):
    for a, c, e in LINES:
        if b[a] and b[a] == b[c] == b[e]:
            return b[a]
    return "D" if all(b) else None


def xo_text(g):
    x = esc(g["p"][0][1]) if g["p"] else "؟"
    o = esc(g["p"][1][1]) if len(g["p"]) > 1 else "؟"
    t = f"⭕ <b>دوز</b>\n❌ {x}   ⚔️   ⭕ {o}\n\n"
    if g["res"] in ("X", "O"):
        return t + f"🏆 <b>{x if g['res'] == 'X' else o} برد!</b>"
    if g["res"] == "D":
        return t + "🤝 مساوی شد"
    if not g["p"]:
        return t + "هر کی خونه‌ای رو بزنه، می‌شه ❌"
    return t + f"نوبت: {'❌' if g['n'] % 2 == 0 else '⭕'}"
