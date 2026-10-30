import asyncio
import html
import json
import logging
import os
import secrets
import time
from pathlib import Path
from urllib.parse import quote

from telegram import (
    BotCommand,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InlineQueryResultsButton,
    InputMediaPhoto,
    InputTextMessageContent,
    KeyboardButton,
    MenuButtonCommands,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from telegram import InlineKeyboardButton as _Btn
from telegram import InlineKeyboardMarkup as Markup
from telegram.error import BadRequest, RetryAfter
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

import admin
import engine
import rewards

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger("donyaye-man")

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise SystemExit("متغیر محیطی BOT_TOKEN تنظیم نشده است.")

BASE = Path(__file__).parent
CONTENT_FILE = BASE / "content.json"
BANNER_FILE = BASE / "banner.jpg"
RAW = "https://raw.githubusercontent.com/hechkim0122/telegram_bot/main/"
BANNER_URL = os.environ.get("BANNER_URL", RAW + "banner.jpg")
BOARD_URL = os.environ.get("BOARD_URL", RAW + "board_snakes.jpg")
LUDO_URL = os.environ.get("LUDO_URL", RAW + "board_ludo.jpg")


def Btn(text, style=None, **kw):
    """دکمه‌ی رنگی: style = primary (آبی) / success (سبز) / danger (قرمز)"""
    if style:
        kw["api_kwargs"] = {"style": style}
    return _Btn(text, **kw)


def KBtn(text, style=None):
    return KeyboardButton(text, api_kwargs={"style": style}) if style else KeyboardButton(text)


def load_content() -> dict:
    with open(CONTENT_FILE, encoding="utf-8") as f:
        return json.load(f)  # هر بار خوانده می‌شود؛ ویرایش فایل نیاز به ری‌استارت ندارد


def tg_link(username: str) -> str:
    return f"https://t.me/{username.lstrip('@')}"


# ---------- کیبوردها ----------

HOME_ROW = [Btn("🏠 منوی اصلی", callback_data="home")]


def home_markup(data):
    s = data["sections"]
    return Markup([
        [Btn("🌐 ورود به وبسایت", "primary", url=data["website_url"])],
        [
            Btn(s["services"]["title"], "primary", callback_data="cat:services"),
            Btn(s["tutorials"]["title"], "success", callback_data="cat:tutorials"),
            Btn(s["games"]["title"], "danger", callback_data="cat:games"),
        ],
        [
            Btn(data["settings"]["title"], callback_data="cat:settings"),
            Btn("💬 پشتیبانی", "success", callback_data="support"),
        ],
    ])


def get_category(data, key):
    return data["settings"] if key == "settings" else data["sections"][key]


def cat_markup(data, key):
    rows = [[Btn(it["title"], callback_data=f"item:{key}:{i}")] for i, it in enumerate(get_category(data, key)["items"])]
    return Markup(rows + [HOME_ROW])


def cat_text(data, key):
    return f"{get_category(data, key)['title']}\n━━━━━━━━━━━━\nیکی از گزینه‌ها رو انتخاب کن 👇"


def support_markup(data):
    return Markup([[Btn("💬 پیام به پشتیبانی", "success", url=tg_link(data["support"]["contact"]))], HOME_ROW])


def bottom_kb(data, uid, bot):
    """دکمه‌های ثابت پایین چت"""
    s = data["sections"]
    miner = KeyboardButton("⛏ استخراج", web_app=WebAppInfo(url=rewards.miner_url(uid, bot)), api_kwargs={"style": "success"})
    return ReplyKeyboardMarkup(
        [
            [KBtn("🏠 صفحه اصلی", "primary"), miner],
            [KBtn(s["services"]["title"], "primary"), KBtn(s["tutorials"]["title"], "success"), KBtn(s["games"]["title"], "danger")],
            [KBtn("👤 حساب من", "primary"), KBtn(data["settings"]["title"]), KBtn("💬 پشتیبانی", "success")],
        ] + ([[KBtn("🛠 پنل مدیریت", "danger")]] if uid == rewards.admin_id() else []),
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="یکی از بخش‌ها رو انتخاب کن…",
    )


async def show(q, text, markup):
    """بنر عکس است؛ پس کپشن را ویرایش می‌کنیم (برای پیام‌های متنی، خود متن)."""
    try:
        if q.message.photo:
            await q.edit_message_caption(caption=text, reply_markup=markup)
        else:
            await q.edit_message_text(text, reply_markup=markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


# ---------- قفل کانال ----------

async def not_joined(context, uid):
    missing = []
    for ch in load_content().get("required_channels", []):
        try:
            m = await context.bot.get_chat_member(ch, uid)
            if m.status in ("left", "kicked"):
                missing.append(ch)
        except Exception as e:  # ربات ادمین کانال نیست؟ کاربر را قفل نکن
            log.warning("بررسی عضویت %s ناموفق بود: %s", ch, e)
    return missing


def lock_view(chs):
    rows = [[Btn(f"📢 عضویت در {c}", "primary", url=tg_link(c))] for c in chs]
    rows.append([Btn("✅ عضو شدم", "success", callback_data="joined")])
    return "🔒 برای استفاده از ربات اول عضو کانال‌های زیر شو، بعد «عضو شدم» رو بزن.", Markup(rows)


async def gate(update, context):
    """True یعنی کاربر اجازه‌ی ادامه دارد. قفل فقط در پیوی ربات اعمال می‌شود."""
    if update.effective_chat.type != "private":
        return True
    u = update.effective_user
    if rewards.is_admin(u):
        await rewards.autoload(context.bot)
    (await rewards.ensure(context.bot, u.id, u.first_name)).pop("fresh", None)  # حساب کاربر از پیام پین‌شده برمی‌گردد
    miss = await not_joined(context, update.effective_user.id)
    if not miss:
        return True
    text, kb = lock_view(miss)
    q = update.callback_query
    if q:
        await show(q, text, kb)
    else:
        await update.effective_message.reply_text(text, reply_markup=kb)
    return False


async def on_joined(update, context):
    q = update.callback_query
    if await not_joined(context, q.from_user.id):
        return await ans(q, "هنوز عضو همه‌ی کانال‌ها نشدی 😅", show_alert=True)
    await ans(q, "✅ خوش اومدی!")
    msg = q.message
    try:
        await msg.delete()
    except Exception:
        pass
    await send_home(update, context)
    await send_kb(msg, context)
    if context.user_data.pop("from_game", False):
        await msg.reply_text("✅ عضو شدی! حالا برگرد به بازی و دوباره دکمه‌ی «بپیوند» (یا خونه‌ی دوز) رو بزن 🎮")


# ---------- صفحه‌ی اصلی ----------

async def send_home(update, context):
    data = load_content()
    u, ch = update.effective_user, update.effective_chat
    if u and ch.type == "private" and (u.username or "").lower() == data["support"]["contact"].lstrip("@").lower():
        context.bot_data["storage"] = ch.id  # برای ساخت تصویر تخته‌ی بازی
        rewards.ADMIN["id"] = ch.id
    markup, msg = home_markup(data), update.effective_message
    hello = (f"سلام {u.first_name} 👋\n\n" if u else "") + data["welcome"]
    if not BANNER_FILE.exists():
        return await msg.reply_text(hello, reply_markup=markup)
    cached = context.bot_data.get("banner_id")
    if cached:
        await msg.reply_photo(cached, caption=hello, reply_markup=markup)
    else:
        with open(BANNER_FILE, "rb") as f:
            sent = await msg.reply_photo(f, caption=hello, reply_markup=markup)
        context.bot_data["banner_id"] = sent.photo[-1].file_id


async def send_kb(msg, context):
    await msg.reply_text("👇 از دکمه‌های پایین هم می‌تونی استفاده کنی.",
                         reply_markup=bottom_kb(load_content(), msg.chat_id, context.bot.username))


async def start_cmd(update, context):
    for a in context.args or []:
        if a == "join":
            context.user_data["from_game"] = True
        elif a.startswith("ref_") and a[4:].isdigit():
            await rewards.set_ref(context.bot, update.effective_user.id, int(a[4:]), update.effective_user.first_name)
    if not await gate(update, context):
        return
    await send_home(update, context)
    await send_kb(update.effective_message, context)


async def account_view(update, context):
    u = update.effective_user
    a = await rewards.ensure(context.bot, u.id, u.first_name)
    link = rewards.ref_link(context.bot.username, u.id)
    text = (f"👤 <b>حساب من</b>\n━━━━━━━━━━━━\n🙋 {html.escape(u.first_name)}\n"
            f"💰 موجودی: <b>${a['bal']:.3f}</b>\n"
            f"👥 دعوت‌های موفق: <b>{a['inv']}</b> (برای برداشت حداقل {rewards.NEED_INV} نفر)\n"
            f"⛏ ضربه‌های امروز: {a['taps']}/{rewards.DAILY}\n💸 مجموع برداشت: ${a['x']:g}\n"
            + (f"⏳ درخواست برداشت در حال بررسی: ${a['pw']:g}\n" if a["pw"] else "")
            + f"\n🔗 لینک دعوت تو:\n<code>{link}</code>\n\n🎁 به ازای هر دوستی که وارد بشه و فعال بشه ${rewards.REF:g} می‌گیری.")
    share = f"https://t.me/share/url?url={quote(link)}&text={quote('بیا تو «دنیای من» 🎮⛏')}"
    await update.effective_message.reply_text(
        text, parse_mode="HTML",
        reply_markup=Markup([[Btn("📤 ارسال لینک دعوت به دوستان", "success", url=share)], HOME_ROW]))


async def on_text(update, context):
    if not await gate(update, context):
        return
    data, t = load_content(), (update.message.text or "").strip()
    s = data["sections"]
    keys = {s["services"]["title"]: "services", s["tutorials"]["title"]: "tutorials",
            s["games"]["title"]: "games", data["settings"]["title"]: "settings"}
    if t in keys:
        return await update.message.reply_text(cat_text(data, keys[t]), reply_markup=cat_markup(data, keys[t]))
    if t == "🛠 پنل مدیریت" and rewards.is_admin(update.effective_user):
        return await admin.panel_cmd(update, context)
    if t == "👤 حساب من":
        return await account_view(update, context)
    if t == "💬 پشتیبانی":
        return await update.message.reply_text(data["support"]["text"], reply_markup=support_markup(data))
    await send_home(update, context)


async def on_webapp(update, context):
    if not await gate(update, context):
        return
    text = await rewards.handle(update, context)
    if text:
        await update.message.reply_text(
            text, reply_markup=bottom_kb(load_content(), update.effective_user.id, context.bot.username))


async def on_button(update, context):
    q = update.callback_query
    if q.data == "joined":
        return await on_joined(update, context)
    await ans(q)
    if not await gate(update, context):
        return
    data, parts = load_content(), q.data.split(":")
    try:
        if parts[0] == "home":
            await show(q, data["welcome"], home_markup(data))
        elif parts[0] == "support":
            await show(q, data["support"]["text"], support_markup(data))
        elif parts[0] == "cat":
            await show(q, cat_text(data, parts[1]), cat_markup(data, parts[1]))
        elif parts[0] == "item":
            key, idx = parts[1], int(parts[2])
            it = get_category(data, key)["items"][idx]
            rows = []
            if it.get("inline"):
                rows.append([Btn("📤 ارسال به چت یا گروه", "success", switch_inline_query=it["inline"])])
            if it.get("url"):
                rows.append([Btn("🔗 مشاهده", "primary", url=it["url"])])
            if it.get("contact"):
                rows.append([Btn("💬 سفارش / پیام به ادمین", "success", url=tg_link(it["contact"]))])
            rows += [[Btn("⬅️ بازگشت", callback_data=f"cat:{key}")], HOME_ROW]
            await show(q, f"{it['title']}\n━━━━━━━━━━━━\n{it['text']}", Markup(rows))
    except (KeyError, IndexError, ValueError):
        log.exception("callback نامعتبر: %s", q.data)
        await show(q, "این بخش پیدا نشد. به منوی اصلی برگرد.", Markup([HOME_ROW]))


# ---------- بازی‌های اینلاین (داخل هر چت) ----------
# وضعیت هر بازی با یک gid یکتا نگه‌داری می‌شود (نه فقط inline_message_id)، چون در چت‌های
# خصوصی ممکن است دو طرف شناسه‌ی متفاوتی برای یک پیام ببینند. همه‌ی شناسه‌ها به‌روز می‌شوند.

async def ans(q, *a, **k):
    """پاسخ به کلیک؛ اگه کلیک قدیمی بود، کل پردازش خراب نشه"""
    try:
        await q.answer(*a, **k)
    except Exception as e:
        log.info("answer ناموفق: %s", e)


def games_db():
    return rewards.DB.setdefault("g", {})


def prune_games():
    g, cut = games_db(), time.time() - 172800
    for k in [k for k, v in g.items() if v.get("ts", 0) < cut]:
        del g[k]


def join_rows():
    """دکمه‌های عضویت کانال‌ها؛ داخل خود پیام بازی نشان داده می‌شوند"""
    return [[Btn(f"📢 عضویت در {c}", "primary", url=tg_link(c))] for c in load_content().get("required_channels", [])]


def sn_kb(g, gid):
    if g["win"] >= 0:
        return Markup([[Btn("🔄 بازی دوباره", "success", callback_data=f"sn:{gid}:again")]])
    if not g["started"]:
        return Markup([
            [Btn(f"➕ بپیوند ({len(g['players'])}/5)", "success", callback_data=f"sn:{gid}:join")],
            [Btn("▶️ شروع بازی", "primary", callback_data=f"sn:{gid}:start")],
        ] + join_rows())
    return Markup([[Btn("🎲 بنداز", "primary", callback_data=f"sn:{gid}:roll")]])


def ld_kb(g, gid):
    if g["win"] >= 0:
        return Markup([[Btn("🔄 بازی دوباره", "success", callback_data=f"ld:{gid}:again")]])
    if not g["started"]:
        return Markup([
            [Btn(f"➕ بپیوند ({len(g['players'])}/5)", "success", callback_data=f"ld:{gid}:join")],
            [Btn("▶️ شروع بازی", "primary", callback_data=f"ld:{gid}:start")],
        ] + join_rows())
    if g["phase"] == "pick":
        e = engine.EMO[g["cols"][g["T"]]]
        return Markup([[Btn(f"{e} مهره {k + 1}", "primary", callback_data=f"ld:{gid}:p{k}") for k in g["sel"]]])
    return Markup([[Btn("🎲 بنداز", "primary", callback_data=f"ld:{gid}:roll")]])


def xo_kb(g, gid):
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            i, v = r * 3 + c, g["b"][r * 3 + c]
            cb = f"xo:{gid}:noop" if (g["res"] or v) else f"xo:{gid}:{i}"
            win = g["res"] in ("X", "O") and i in engine.xo_line(g["b"])
            row.append(Btn({"X": "❌", "O": "⭕"}.get(v, "▫️"), "success" if win else {"X": "danger", "O": "primary"}.get(v), callback_data=cb))
        rows.append(row)
    if g["res"]:
        rows.append([Btn("🔄 دور بعد", "success", callback_data=f"xo:{gid}:again")])
    return Markup(rows + (join_rows() if len(g["p"]) < 2 else []))


async def need_join(context, q):
    """بازیکن باید عضو کانال‌ها باشد؛ لینک عضویت زیر خود بازی است، لازم نیست وارد ربات شود."""
    miss = await not_joined(context, q.from_user.id)
    if not miss:
        return True
    await ans(q, "🔒 اول با دکمه‌های عضویت زیر بازی، عضو این کانال‌ها شو و دوباره بزن:\n" + "\n".join(miss), show_alert=True)
    return False


async def inline_query(update, context):
    # فرستنده‌ی بازی هم باید عضو کانال‌ها باشد
    if await not_joined(context, update.inline_query.from_user.id):
        return await update.inline_query.answer(
            [], cache_time=0,
            button=InlineQueryResultsButton(text="🔒 اول عضو کانال‌ها شو", start_parameter="join"))
    q = update.inline_query.query.strip().lower()
    res = []
    if q in ("", "snakes"):
        gid, g = secrets.token_hex(4), engine.sn_new()
        res.append(InlineQueryResultPhoto(
            id=f"s{gid}", photo_url=BOARD_URL, thumbnail_url=BANNER_URL,
            title="🐍 مارپله", description="۲ تا ۵ نفره، با تصویر زنده",
            caption=engine.sn_caption(g), parse_mode="HTML", reply_markup=sn_kb(g, gid)))
    if q in ("", "ludo"):
        gid, g = secrets.token_hex(4), engine.ld_new()
        res.append(InlineQueryResultPhoto(
            id=f"l{gid}", photo_url=LUDO_URL, thumbnail_url=BANNER_URL,
            title="🎲 منچ", description="۲ تا ۵ نفره، با تصویر زنده",
            caption=engine.ld_caption(g), parse_mode="HTML", reply_markup=ld_kb(g, gid)))
    if q in ("", "xo"):
        gid, g = secrets.token_hex(4), engine.xo_new()
        res.append(InlineQueryResultArticle(
            id=f"x{gid}", title="⭕ دوز", description="۲ نفره",
            input_message_content=InputTextMessageContent(engine.xo_text(g), parse_mode="HTML"),
            reply_markup=xo_kb(g, gid)))
    await update.inline_query.answer(res, cache_time=0, is_personal=True)


async def game_cmd(update, context):
    await update.effective_message.reply_text(
        "🎮 بازی رو انتخاب کن و به هر چت یا گروهی بفرست. نیازی نیست ربات عضو اون چت باشه.",
        reply_markup=Markup([
            [Btn("🐍 مارپله", "success", switch_inline_query="snakes")],
            [Btn("🎲 منچ", "danger", switch_inline_query="ludo")],
            [Btn("⭕ دوز", "primary", switch_inline_query="xo")],
        ]),
    )


async def photo_id(context, jpg):
    """تصویر رو یک بار داخل چت ادمین می‌فرسته تا file_id بگیره (برای ویرایش پیام اینلاین)"""
    chat = rewards.admin_id()
    if not chat:
        raise RuntimeError("storage chat not set")
    for attempt in (1, 2):
        try:
            m = await context.bot.send_photo(chat, jpg)
            break
        except RetryAfter as e:
            if attempt == 2:
                raise
            await asyncio.sleep(e.retry_after + 1)
    fid = m.photo[-1].file_id
    try:
        await m.delete()
    except Exception:
        pass
    return fid


async def edit_all(g, fn):
    for mid in list(g["mids"]):
        try:
            await fn(mid)
        except BadRequest as e:
            if "not modified" not in str(e).lower():
                log.warning("ویرایش پیام بازی ناموفق: %s", e)
        except Exception as e:
            log.warning("ویرایش پیام بازی ناموفق: %s", e)


def track(g, mid):
    if mid not in g["mids"]:
        g["mids"].append(mid)
    g["ts"] = time.time()
    rewards.touch()


async def on_game(update, context):
    q = update.callback_query
    mid = q.inline_message_id
    if not mid:
        return await ans(q, "این بازی رو از طریق ارسال اینلاین بفرست.", show_alert=True)
    kind, gid, act = q.data.split(":", 2)
    if act == "noop":
        return await ans(q)
    u, name = q.from_user, q.from_user.first_name
    try:
        if kind in GAMES:
            await board_cb(context, q, kind, gid, mid, act, u, name)
        elif act == "again":
            await xo_again_cb(context, q, gid, mid, u)
        else:
            await xo_cb(context, q, gid, mid, int(act), u, name)
    except Exception:
        log.exception("خطا در بازی")


def sn_start(g):
    g["started"], g["pos"] = True, [0] * len(g["players"])


def sn_play(g, act, u):
    """None = حرکت انجام شد، "" = نادیده بگیر، متن = پیام کوتاه به بازیکن"""
    if act != "roll" or not g["started"] or g["win"] >= 0:
        return ""
    if u.id != g["players"][g["T"]][0]:
        return "نوبت تو نیست 😅"
    engine.sn_roll(g)


def ld_play(g, act, u):
    if not g["started"] or g["win"] >= 0:
        return ""
    if u.id != g["players"][g["T"]][0]:
        return "نوبت تو نیست 😅"
    if act == "roll" and g["phase"] == "roll":
        engine.ld_roll(g)
    elif act[:1] == "p" and act[1:].isdigit() and g["phase"] == "pick" and int(act[1:]) in g["sel"]:
        engine.ld_move(g, int(act[1:]))
    else:
        return ""


GAMES = {
    "sn": dict(new=engine.sn_new, start=sn_start, again=engine.sn_again, play=sn_play, key="games_sn",
               caption=engine.sn_caption, kb=sn_kb,
               jpg=lambda g: engine.render_board(g["pos"], g["T"] if g["win"] < 0 else g["win"])),
    "ld": dict(new=engine.ld_new, start=engine.ld_start, again=engine.ld_again, play=ld_play, key="games_ld",
               caption=engine.ld_caption, kb=ld_kb, jpg=engine.render_ludo),
}


async def board_cb(context, q, kind, gid, mid, act, u, name):
    """مارپله و منچ: عضویت، شروع، دور بعد و حرکت‌ها یک مسیر مشترک دارن"""
    S, games = GAMES[kind], games_db()
    g = games.get(gid)
    if act == "join":
        if not await need_join(context, q):
            return
        g = games.setdefault(gid, {**S["new"](), "mids": []})
        track(g, mid)
        if g["started"]:
            return await ans(q, "بازی شروع شده.", show_alert=True)
        if any(p[0] == u.id for p in g["players"]):
            return await ans(q, "تو قبلاً پیوستی ✅")
        if len(g["players"]) >= 5:
            return await ans(q, "ظرفیت پر شده.", show_alert=True)
        g["players"].append([u.id, name])
    elif not g:
        return await ans(q, "این بازی منقضی شده. یه بازی جدید بفرست.", show_alert=True)
    else:
        track(g, mid)
        if act == "start":
            if g["started"]:
                return await ans(q)
            if not g["players"] or g["players"][0][0] != u.id:
                return await ans(q, "فقط نفر اول (میزبان) می‌تونه بازی رو شروع کنه.", show_alert=True)
            if len(g["players"]) < 2:
                return await ans(q, "حداقل ۲ نفر لازمه.", show_alert=True)
            S["start"](g)
            rewards.bump(S["key"])
        elif act == "again":
            if g["win"] < 0:
                return await ans(q)
            if not any(p[0] == u.id for p in g["players"]):
                return await ans(q, "فقط بازیکن‌های همین بازی می‌تونن دور بعد رو شروع کنن.", show_alert=True)
            S["again"](g)
            rewards.bump(S["key"])
        else:
            err = S["play"](g, act, u)
            if err is not None:
                return await (ans(q, err) if err else ans(q))
    await ans(q)
    rewards.touch()
    cap, kb, fid = S["caption"](g), S["kb"](g, gid), None
    if g["started"]:
        try:
            fid = await photo_id(context, await asyncio.to_thread(S["jpg"], g))
        except Exception as e:
            log.warning("تصویر ساخته نشد؛ فقط متن به‌روز می‌شود: %s", e)

    async def one(m):
        if fid:
            await context.bot.edit_message_media(inline_message_id=m, media=InputMediaPhoto(fid, caption=cap, parse_mode="HTML"), reply_markup=kb)
        else:
            await context.bot.edit_message_caption(inline_message_id=m, caption=cap, parse_mode="HTML", reply_markup=kb)
    await edit_all(g, one)


async def xo_cb(context, q, gid, mid, cell, u, name):
    games = games_db()
    g = games.setdefault(gid, {**engine.xo_new(), "mids": []})
    track(g, mid)
    if g["res"] or g["b"][cell]:
        return await ans(q)
    idx = g["n"] % 2
    if len(g["p"]) <= idx:
        if any(p[0] == u.id for p in g["p"]):
            return await ans(q, "منتظر حریف باش 😉")
        if not await need_join(context, q):
            return
        g["p"].append([u.id, name])
        if len(g["p"]) == 2:
            rewards.bump("games_xo")
    elif g["p"][idx][0] != u.id:
        return await ans(q, "نوبت تو نیست 😅")
    g["b"][cell] = "X" if idx == 0 else "O"
    g["n"] += 1
    g["res"] = engine.xo_result(g["b"])
    await ans(q)
    rewards.touch()
    txt, kb = engine.xo_text(g), xo_kb(g, gid)
    await edit_all(g, lambda m: context.bot.edit_message_text(inline_message_id=m, text=txt, parse_mode="HTML", reply_markup=kb))


async def xo_again_cb(context, q, gid, mid, u):
    g = games_db().get(gid)
    if not g:
        return await ans(q, "این بازی منقضی شده. یه بازی جدید بفرست.", show_alert=True)
    track(g, mid)
    if not g["res"]:
        return await ans(q)
    if not any(p[0] == u.id for p in g["p"]):
        return await ans(q, "فقط بازیکن‌های همین بازی می‌تونن دور بعد رو شروع کنن.", show_alert=True)
    engine.xo_again(g)
    rewards.bump("games_xo")
    await ans(q)
    txt, kb = engine.xo_text(g), xo_kb(g, gid)
    await edit_all(g, lambda m: context.bot.edit_message_text(inline_message_id=m, text=txt, parse_mode="HTML", reply_markup=kb))


async def run():
    app = ApplicationBuilder().token(TOKEN).build()
    rewards.cfg, rewards.joined = load_content, not_joined
    rewards.kb = lambda uid: bottom_kb(load_content(), uid, app.bot.username)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, admin.msg), group=-1)
    app.add_handler(CommandHandler(["start", "menu"], start_cmd))
    app.add_handler(CommandHandler("game", game_cmd))
    app.add_handler(CommandHandler("admin", admin.panel_cmd))
    app.add_handler(ChatMemberHandler(admin.on_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(CallbackQueryHandler(on_game, pattern=r"^(sn|ld|xo):"))
    app.add_handler(CallbackQueryHandler(rewards.on_wd, pattern=r"^wd:"))
    app.add_handler(CallbackQueryHandler(admin.cb, pattern=r"^adm:"))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_webapp))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, on_text))

    # RUN_SECONDS: برای GitHub Actions؛ بعد از این مدت خاموش می‌شود تا اجرای بعدی ادامه دهد.
    run_seconds = int(os.environ.get("RUN_SECONDS", "0"))

    async def saver():
        while True:
            await asyncio.sleep(30)
            prune_games()
            await rewards.retry(app.bot)
            if rewards.admin_id():
                await rewards.save(app.bot, rewards.admin_id())

    async with app:
        try:  # دکمه‌ی منو (پایین سمت چپ کادر پیام) و لیست دستورها
            await app.bot.set_my_commands([
                BotCommand("start", "🚀 شروع دوباره"),
                BotCommand("menu", "🏠 صفحه اصلی"),
                BotCommand("game", "🎮 بازی‌ها"),
            ])
            await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        except Exception:
            log.exception("تنظیم دستورها ناموفق بود")
        if rewards.admin_id():
            await rewards.autoload(app.bot)
        else:
            log.warning("admin_id تنظیم نشده؛ ادمین با یوزرنیم شناخته می‌شود و فهرست کاربران بعد از ری‌استارت دیرتر بالا می‌آید.")
        await app.start()
        await app.updater.start_polling()
        task = asyncio.create_task(saver())
        log.info("ربات روشن شد.")
        if run_seconds > 0:
            await asyncio.sleep(run_seconds)
            log.info("زمان اجرا تمام شد؛ خاموش می‌شوم تا اجرای بعدی ادامه دهد.")
        else:
            await asyncio.Event().wait()
        task.cancel()
        await app.updater.stop()
        await rewards.retry(app.bot)
        if rewards.admin_id():
            await rewards.save(app.bot, rewards.admin_id())
        await app.stop()


if __name__ == "__main__":
    asyncio.run(run())
