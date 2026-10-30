"""منطق بازی‌ها (مارپله، منچ، دوز) و ساخت تصویر. بدون وابستگی به تلگرام."""
import html
import io
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).parent
esc = html.escape
EMO = ["🦁", "🐉", "🌳", "🔥", "🐺"]  # شیر، اژدها، درخت، ققنوس، گرگ (هم‌ترتیب با coins.png)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_A = {}


def _font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default(size=size)


def _assets():
    if not _A:
        _A["snakes"] = Image.open(BASE / "board_snakes.jpg").convert("RGBA")
        _A["ludo"] = Image.open(BASE / "board_ludo.jpg").convert("RGBA")
        sheet = Image.open(BASE / "coins.png").convert("RGBA")
        h = sheet.height
        _A["sheet"] = [sheet.crop((i * h, 0, (i + 1) * h, h)) for i in range(5)]
        _A["cfg"] = json.loads((BASE / "ludo_layout.json").read_text(encoding="utf-8"))
        _A["sized"] = {}
    return _A


def _coin(i, size):
    A = _assets()
    if (i, size) not in A["sized"]:
        A["sized"][(i, size)] = A["sheet"][i].resize((size, size), Image.LANCZOS)
    return A["sized"][(i, size)]


def _put(im, cx, cy, i, size, ring=False, label=None):
    """گذاشتن مهره‌ی i با سایه روی تصویر؛ ring = حلقه‌ی انتخاب، label = شماره‌ی مهره"""
    x, y = int(cx - size / 2), int(cy - size / 2)
    sh = Image.new("RGBA", (size + 16, size + 16), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([5, 9, size + 5, size + 9], fill=(0, 0, 0, 120))
    im.alpha_composite(sh, (x - 5, y - 4))
    im.alpha_composite(_coin(i, size), (x, y))
    d = ImageDraw.Draw(im)
    if ring:
        d.ellipse([x - 6, y - 6, x + size + 6, y + size + 6], outline=(255, 255, 255, 255), width=5)
        d.ellipse([x - 9, y - 9, x + size + 9, y + size + 9], outline=(0, 0, 0, 160), width=2)
    if label:
        bx, by = x + size - 6, y + size - 6
        d.ellipse([bx - 11, by - 11, bx + 11, by + 11], fill=(255, 255, 255, 240), outline=(30, 30, 30, 255), width=2)
        d.text((bx, by), str(label), font=_font(17), fill=(20, 20, 20), anchor="mm")


def _jpeg(im):
    buf = io.BytesIO()
    im.convert("RGB").resize((1000, 1000), Image.LANCZOS).save(buf, "JPEG", quality=88)
    return buf.getvalue()


# ---------- مارپله ----------
# مار و نردبان‌ها دقیقاً مطابق تصویر board_snakes.jpg
SNAKES = {92: 55, 82: 41, 77: 44, 70: 11, 47: 15}
LADDERS = {3: 24, 20: 43, 28: 49, 36: 56, 48: 72, 58: 78, 65: 87, 71: 91}
M, CELL, COIN = 77, 110, 56
LAYOUT = {
    1: [(0, 0)], 2: [(-24, 0), (24, 0)], 3: [(-24, -18), (24, -18), (0, 22)],
    4: [(-24, -20), (24, -20), (-24, 20), (24, 20)], 5: [(-24, -20), (24, -20), (-24, 20), (24, 20), (0, 0)],
}


def xy(n):
    r, c = divmod(n - 1, 10)
    if r % 2:
        c = 9 - c
    return M + CELL * (c + .5), M + CELL * (9 - r + .5)


def render_board(pos, turn=None):
    im = _assets()["snakes"].copy()
    groups = {}
    for i, p in enumerate(pos):
        groups.setdefault(max(p, 1), []).append(i)
    for cell, ids in groups.items():
        cx, cy = xy(cell)
        for k, i in enumerate(ids):
            ox, oy = LAYOUT[len(ids)][k]
            _put(im, cx + ox, cy + oy, i, COIN, ring=(turn is not None and i == turn))
    return _jpeg(im)


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


def bar(p):
    n = min(p // 10, 10)
    return "▰" * n + "▱" * (10 - n)


def sn_again(g):
    """بازی دوباره با همان بازیکن‌ها؛ نفر بعد از برنده شروع می‌کند"""
    n = len(g["players"])
    g["T"] = (g["win"] + 1) % n if g["win"] >= 0 else 0
    g["pos"], g["win"], g["msg"], g["started"] = [0] * n, -1, "", True


def sn_caption(g):
    lines = ["🐍 <b>مارپله</b>", "━━━━━━━━━━━━"]
    if not g["players"]:
        return "\n".join(lines) + "\nهنوز کسی نپیوسته. ۲ تا ۵ نفر بپیوندن 👇"
    for i, (_, n) in enumerate(g["players"]):
        if g["started"]:
            mark = "👉 " if i == g["T"] and g["win"] < 0 else ""
            lines.append(f"{mark}{EMO[i]} <b>{esc(n)}</b> — خونه {g['pos'][i]}\n      {bar(g['pos'][i])}")
        else:
            lines.append(f"{EMO[i]} {esc(n)}" + (" 👑" if i == 0 else ""))
    if not g["started"]:
        lines += ["", f"👥 {len(g['players'])}/5 نفر  •  👑 میزبان بازی رو شروع می‌کنه"]
    else:
        lines.append("")
        if g["msg"]:
            lines.append(g["msg"])
        if g["win"] >= 0:
            lines.append(f"🏆 <b>{esc(g['players'][g['win']][1])}</b> برنده شد! 🎉")
        else:
            lines.append(("" if g["msg"] else "🎲 بازی شروع شد!\n") + f"نوبت: {EMO[g['T']]} <b>{esc(g['players'][g['T']][1])}</b>")
    return "\n".join(lines)


# ---------- منچ ۲ تا ۵ نفره ----------
# هر بازیکن ۴ مهره دارد. وضعیت مهره (r): -1 = پایگاه، 0..63 = مسیر اصلی، 64..68 = ستون ورودی، 69 = رسیده
LAP, HOME_END = 64, 69
COIN_L = 48


def ld_new():
    return {"players": [], "started": False, "cols": [], "tok": [], "T": 0, "D": 0, "sel": [],
            "phase": "roll", "six": 0, "msg": "", "win": -1}


def ld_start(g, first=0):
    n = len(g["players"])
    g["cols"] = _assets()["cfg"]["arms"][str(n)]
    g["tok"] = [[-1] * 4 for _ in range(n)]
    g["T"], g["D"], g["sel"], g["phase"], g["six"], g["msg"], g["win"], g["started"] = first, 0, [], "roll", 0, "", -1, True


def ld_again(g):
    ld_start(g, (g["win"] + 1) % len(g["players"]) if g["win"] >= 0 else 0)


def _track_idx(g, i, r):
    """شماره‌ی خونه‌ی مسیر مشترک (یا None اگر روی مسیر مشترک نیست)"""
    if 0 <= r < LAP:
        cfg = _assets()["cfg"]
        return (cfg["start"][str(g["cols"][i])] + r) % len(cfg["track"])
    return None


def ld_movable(g, i, d):
    seen, out = set(), []
    for k, r in enumerate(g["tok"][i]):
        if (d == 6 if r < 0 else r + d <= HOME_END) and r not in seen:  # مهره‌های هم‌وضعیت یکی حساب می‌شن
            seen.add(r)
            out.append(k)
    return out


def _next(g):
    g["T"] = (g["T"] + 1) % len(g["players"])
    g["six"], g["phase"], g["sel"] = 0, "roll", []


def ld_roll(g):
    i, d = g["T"], random.randint(1, 6)
    g["D"] = d
    g["six"] = g["six"] + 1 if d == 6 else 0
    name = esc(g["players"][i][1])
    if g["six"] >= 3:
        g["msg"] = f"{name}: 🎲 6 — سه تا ۶ پشت‌هم! نوبتش سوخت 😬"
        return _next(g)
    mv = ld_movable(g, i, d)
    if not mv:
        g["msg"] = f"{name}: 🎲 {d} — حرکتی نداره 😅"
        return _next(g)
    g["msg"] = f"{name}: 🎲 {d}"
    if len(mv) == 1:
        return ld_move(g, mv[0])
    g["phase"], g["sel"] = "pick", mv


def ld_move(g, k):
    i, d = g["T"], g["D"]
    t = g["tok"][i]
    t[k] = 0 if t[k] < 0 else t[k] + d
    extra, note = d == 6, []
    if t[k] == HOME_END:
        extra = True
        note.append("🏁 یه مهره به مقصد رسید!")
        if all(r == HOME_END for r in t):
            g["win"], g["phase"], g["sel"] = i, "roll", []
            g["msg"] += " " + note[0]
            return
    idx = _track_idx(g, i, t[k])
    if idx is not None and idx not in _assets()["cfg"]["safe"]:
        for j, other in enumerate(g["tok"]):
            if j != i:
                for m, r in enumerate(other):
                    if _track_idx(g, j, r) == idx:
                        other[m] = -1
                        extra = True
                        note.append(f"💥 مهره‌ی {EMO[g['cols'][j]]} زده شد!")
    if note:
        g["msg"] += " " + " ".join(dict.fromkeys(note))
    if extra:
        g["phase"], g["sel"] = "roll", []
        g["msg"] += " (نوبت اضافه ✨)"
    else:
        _next(g)


def _ld_pos(g, i, k):
    cfg, arm, r = _assets()["cfg"], str(g["cols"][i]), g["tok"][i][k]
    if r < 0:
        return cfg["base"][arm][k]
    if r < LAP:
        return cfg["track"][_track_idx(g, i, r)]
    if r < HOME_END:
        return cfg["home"][arm][r - LAP]
    return cfg["finish"][arm][k]


def render_ludo(g=None):
    im = _assets()["ludo"].copy()
    if g and g["started"]:
        stacks = {}
        for i in range(len(g["players"])):
            for k in range(4):
                x, y = _ld_pos(g, i, k)
                stacks.setdefault((round(x), round(y)), []).append((i, k, x, y))
        pick = g["phase"] == "pick" and g["win"] < 0
        for items in stacks.values():
            items.sort(key=lambda t: pick and t[0] == g["T"] and t[1] in g["sel"])  # قابل‌انتخاب‌ها بالا
            for n, (i, k, x, y) in enumerate(items):
                r = g["tok"][i][k]
                size = 38 if r == HOME_END else COIN_L
                _put(im, x + n * 9, y - n * 9, g["cols"][i], size,
                     ring=pick and i == g["T"] and k in g["sel"], label=k + 1)
    return _jpeg(im)


def ld_caption(g):
    lines = ["🎲 <b>منچ</b>", "━━━━━━━━━━━━"]
    if not g["players"]:
        return "\n".join(lines) + "\nهنوز کسی نپیوسته. ۲ تا ۵ نفر بپیوندن 👇"
    for i, (_, n) in enumerate(g["players"]):
        if not g["started"]:
            lines.append(f"👤 {esc(n)}" + (" 👑" if i == 0 else ""))
            continue
        t = g["tok"][i]
        done, base = sum(r == HOME_END for r in t), sum(r < 0 for r in t)
        mark = "👉 " if i == g["T"] and g["win"] < 0 else ""
        lines.append(f"{mark}{EMO[g['cols'][i]]} <b>{esc(n)}</b> — 🏁 {done}/4  🏠 {base}")
    if not g["started"]:
        lines += ["", f"👥 {len(g['players'])}/5 نفر  •  👑 میزبان بازی رو شروع می‌کنه",
                  "💡 با ۶ مهره از پایگاه خارج می‌شه؛ ۶ و زدن مهره‌ی رقیب نوبت اضافه می‌ده."]
        return "\n".join(lines)
    lines.append("")
    if g["msg"]:
        lines.append(g["msg"])
    if g["win"] >= 0:
        lines.append(f"🏆 <b>{esc(g['players'][g['win']][1])}</b> برنده شد! 🎉")
    elif g["phase"] == "pick":
        lines.append(f"{EMO[g['cols'][g['T']]]} <b>{esc(g['players'][g['T']][1])}</b>، مهره‌ات رو انتخاب کن 👇")
    else:
        lines.append(("" if g["msg"] else "🎲 بازی شروع شد!\n") + f"نوبت: {EMO[g['cols'][g['T']]]} <b>{esc(g['players'][g['T']][1])}</b>")
    return "\n".join(lines)


# ---------- دوز ----------
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def xo_new():
    return {"p": [], "b": [""] * 9, "n": 0, "res": None}


def xo_line(b):
    for l in LINES:
        if b[l[0]] and b[l[0]] == b[l[1]] == b[l[2]]:
            return l
    return ()


def xo_result(b):
    if xo_line(b):
        return b[xo_line(b)[0]]
    return "D" if all(b) else None


def xo_again(g):
    """دور بعد: جای ❌ و ⭕ عوض می‌شود"""
    g["p"].reverse()
    g["b"], g["n"], g["res"] = [""] * 9, 0, None


def xo_text(g):
    x = esc(g["p"][0][1]) if g["p"] else "؟"
    o = esc(g["p"][1][1]) if len(g["p"]) > 1 else "؟"
    t = f"⭕ <b>دوز</b>\n━━━━━━━━━━━━\n❌ {x}   ⚔️   ⭕ {o}\n\n"
    if g["res"] in ("X", "O"):
        return t + f"🏆 <b>{x if g['res'] == 'X' else o}</b> برد! 🎉"
    if g["res"] == "D":
        return t + "🤝 مساوی شد"
    if not g["p"]:
        return t + "هر کی خونه‌ای رو بزنه، می‌شه ❌"
    if len(g["p"]) < 2:
        return t + "⏳ منتظر حریف… یکی دیگه خونه‌ی خالی رو بزنه"
    return t + f"نوبت: {'❌ ' + x if g['n'] % 2 == 0 else '⭕ ' + o}"
