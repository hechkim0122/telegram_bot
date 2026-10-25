"""منطق بازی‌ها و ساخت تصویر. بدون وابستگی به تلگرام."""
import html
import io
import random

from PIL import Image, ImageDraw, ImageFont

SNAKES = {16: 6, 47: 26, 49: 11, 56: 53, 62: 19, 64: 60, 87: 24, 93: 73, 95: 75, 98: 78}
LADDERS = {1: 38, 4: 14, 9: 31, 21: 42, 28: 84, 36: 44, 51: 67, 71: 91, 80: 100}
COLORS = [(239, 68, 68), (34, 197, 94), (59, 130, 246), (234, 179, 8), (168, 85, 247)]
EMO = ["🔴", "🟢", "🔵", "🟡", "🟣"]
CELL = 64
esc = html.escape


def xy(n):
    r, c = divmod(n - 1, 10)
    if r % 2:
        c = 9 - c
    return c * CELL + CELL // 2, (9 - r) * CELL + CELL // 2


def render_board(pos):
    S = CELL * 10
    im = Image.new("RGB", (S, S + 50), (16, 17, 42))
    d = ImageDraw.Draw(im)
    f = ImageFont.load_default(size=14)
    for n in range(1, 101):
        x, y = xy(n)
        d.rectangle([x - 32, y - 32, x + 32, y + 32], fill=(38, 42, 104) if n % 2 else (48, 53, 127))
        d.text((x - 29, y - 29), str(n), fill=(139, 144, 214), font=f)
    for a, b in LADDERS.items():
        d.line([xy(a), xy(b)], fill=(161, 98, 7), width=12)
        d.line([xy(a), xy(b)], fill=(253, 230, 138), width=3)
    for a, b in SNAKES.items():
        (x1, y1), (x2, y2) = xy(a), xy(b)
        cx, cy = (x1 + x2) / 2 + (y2 - y1) * .25, (y1 + y2) / 2 - (x2 - x1) * .25
        pts = [((1 - t) ** 2 * x1 + 2 * t * (1 - t) * cx + t * t * x2,
                (1 - t) ** 2 * y1 + 2 * t * (1 - t) * cy + t * t * y2) for t in (i / 20 for i in range(21))]
        d.line(pts, fill=(22, 163, 74), width=11, joint="curve")
        d.ellipse([x1 - 13, y1 - 13, x1 + 13, y1 + 13], fill=(220, 38, 38))
    for i, p in enumerate(pos):
        x, y = xy(p) if p else (40 + i * 50, S + 25)
        ox, oy = ((i % 3 - 1) * 18, (i // 3) * 18 - 9) if p else (0, 0)
        d.ellipse([x + ox - 14, y + oy - 14, x + ox + 14, y + oy + 14], fill=COLORS[i], outline="white", width=3)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
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
