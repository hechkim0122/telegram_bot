import asyncio
import json
import logging
import os
from pathlib import Path

from telegram import InlineKeyboardButton as _Btn
from telegram import (
    InlineKeyboardMarkup as Markup,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InputMediaPhoto,
    InputTextMessageContent,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO
)
log = logging.getLogger("donyaye-man")

import engine

BANNER_URL = os.environ.get(
    "BANNER_URL", "https://raw.githubusercontent.com/hechkim0122/telegram_bot/main/banner.jpg"
)


def Btn(text, style=None, **kw):
    """دکمه‌ی رنگی: style = primary (آبی) / success (سبز) / danger (قرمز)"""
    if style:
        kw["api_kwargs"] = {"style": style}
    return _Btn(text, **kw)

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise SystemExit("متغیر محیطی BOT_TOKEN تنظیم نشده است.")

BASE = Path(__file__).parent
CONTENT_FILE = BASE / "content.json"
BANNER_FILE = BASE / "banner.jpg"


def load_content() -> dict:
    # هر بار خوانده می‌شود تا با ویرایش content.json نیازی به ری‌استارت نباشد
    with open(CONTENT_FILE, encoding="utf-8") as f:
        return json.load(f)


def tg_link(username: str) -> str:
    return f"https://t.me/{username.lstrip('@')}"


# ---------- کیبوردها ----------

def home_markup(data: dict) -> Markup:
    s = data["sections"]
    return Markup(
        [
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
        ]
    )


def get_category(data: dict, key: str) -> dict:
    return data["settings"] if key == "settings" else data["sections"][key]


def back_row(key: str):
    return [Btn("⬅️ بازگشت", callback_data=f"cat:{key}")]


HOME_ROW = [Btn("🏠 منوی اصلی", callback_data="home")]


# ---------- نمایش پیام ----------

async def show(q, text: str, markup: Markup):
    """پیام اولیه عکس (بنر) است؛ پس کپشن را ویرایش می‌کنیم."""
    try:
        if q.message.photo:
            await q.edit_message_caption(caption=text, reply_markup=markup)
        else:
            await q.edit_message_text(text, reply_markup=markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def send_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_content()
    u, ch = update.effective_user, update.effective_chat
    if u and ch.type == "private" and (u.username or "").lower() == data["support"]["contact"].lstrip("@").lower():
        context.bot_data["storage"] = ch.id
    markup = home_markup(data)
    msg = update.effective_message

    if not BANNER_FILE.exists():
        await msg.reply_text(data["welcome"], reply_markup=markup)
        return

    cached = context.bot_data.get("banner_id")
    if cached:
        await msg.reply_photo(cached, caption=data["welcome"], reply_markup=markup)
    else:
        with open(BANNER_FILE, "rb") as f:
            sent = await msg.reply_photo(f, caption=data["welcome"], reply_markup=markup)
        context.bot_data["banner_id"] = sent.photo[-1].file_id


# ---------- بازی آنلاین ----------

def game_code(context, game: str) -> str:
    return f"{game}_{secrets.token_hex(4)}"


def invite_url(context, code: str) -> str:
    link = f"https://t.me/{context.bot.username}?startapp={code}"
    return "https://t.me/share/url?url=" + quote(link) + "&text=" + quote("بیا با هم بازی کنیم 🎮")


async def game_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """در گروه یا پیوی: /game  ← هر دکمه یک اتاق مشترک برای همه‌ی اعضا است."""
    data = load_content()
    rows = []
    for it in data["sections"]["games"]["items"]:
        if it.get("game"):
            code = game_code(context, it["game"])
            rows.append([Btn(it["title"], url=f"https://t.me/{context.bot.username}?startapp={code}")])
    await update.effective_message.reply_text(
        "🎮 یه بازی انتخاب کن. هر کسی دکمه رو بزنه وارد همون اتاق می‌شه.",
        reply_markup=Markup(rows),
    )


# ---------- هندلرها ----------

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = load_content()
    parts = q.data.split(":")

    try:
        if parts[0] == "home":
            await show(q, data["welcome"], home_markup(data))

        elif parts[0] == "support":
            sup = data["support"]
            rows = [
                [Btn("💬 پیام به پشتیبانی", "success", url=tg_link(sup["contact"]))],
                HOME_ROW,
            ]
            await show(q, sup["text"], Markup(rows))

        elif parts[0] == "cat":
            key = parts[1]
            cat = get_category(data, key)
            rows = [
                [Btn(it["title"], callback_data=f"item:{key}:{i}")]
                for i, it in enumerate(cat["items"])
            ]
            rows.append(HOME_ROW)
            await show(q, cat["title"], Markup(rows))

        elif parts[0] == "item":
            key, idx = parts[1], int(parts[2])
            it = get_category(data, key)["items"][idx]
            rows = []
            if it.get("game"):
                code = game_code(context, it["game"])
                rows.append([Btn("🎮 ورود به بازی", web_app=WebAppInfo(url=f"{data['games_base']}?p={code}"))])
                rows.append([Btn("📤 دعوت دوست", url=invite_url(context, code))])
            if it.get("inline"):
                rows.append([Btn("📤 ارسال به چت یا گروه", "success", switch_inline_query=it["inline"])])
            if it.get("url"):
                rows.append([Btn("🔗 مشاهده", "primary", url=it["url"])])
            if it.get("contact"):
                rows.append([Btn("💬 سفارش / پیام به ادمین", "success", url=tg_link(it["contact"]))])
            rows.append(back_row(key))
            rows.append(HOME_ROW)
            await show(q, f"{it['title']}\n\n{it['text']}", Markup(rows))

    except (KeyError, IndexError, ValueError):
        log.exception("callback نامعتبر: %s", q.data)
        await show(q, "این بخش پیدا نشد. به منوی اصلی برگرد.", Markup([HOME_ROW]))


# ---------- بازی‌های اینلاین (داخل هر چت) ----------

def sn_kb(g):
    if g["win"] >= 0:
        return Markup([[Btn("🏆 بازی تموم شد", callback_data="sn:noop")]])
    if not g["started"]:
        return Markup([
            [Btn("➕ بپیوند", "success", callback_data="sn:join")],
            [Btn("▶️ شروع بازی (میزبان)", "primary", callback_data="sn:start")],
        ])
    return Markup([[Btn("🎲 بنداز", "primary", callback_data="sn:roll")]])


def xo_kb(g):
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            i = r * 3 + c
            v = g["b"][i]
            cb = "xo:noop" if (g["res"] or v) else f"xo:{i}"
            row.append(Btn({"X": "❌", "O": "⭕"}.get(v, "▫️"), {"X": "danger", "O": "primary"}.get(v), callback_data=cb))
        rows.append(row)
    return Markup(rows)


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.inline_query.query.strip().lower()
    res = []
    if q in ("", "snakes"):
        g = engine.sn_new()
        res.append(InlineQueryResultPhoto(
            id="snakes", photo_url=BANNER_URL, thumbnail_url=BANNER_URL,
            title="🐍 مارپله", description="۲ تا ۵ نفره، با تصویر زنده",
            caption=engine.sn_caption(g), parse_mode="HTML", reply_markup=sn_kb(g)))
    if q in ("", "xo"):
        g = engine.xo_new()
        res.append(InlineQueryResultArticle(
            id="xo", title="⭕ دوز", description="۲ نفره",
            input_message_content=InputTextMessageContent(engine.xo_text(g), parse_mode="HTML"),
            reply_markup=xo_kb(g)))
    await update.inline_query.answer(res, cache_time=30)


async def game_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🎮 بازی رو انتخاب کن و به هر چت یا گروهی بفرست. نیازی نیست ربات عضو اون چت باشه.",
        reply_markup=Markup([
            [Btn("🐍 مارپله", "success", switch_inline_query="snakes")],
            [Btn("⭕ دوز", "primary", switch_inline_query="xo")],
        ]),
    )


async def board_file_id(context, pos):
    chat = load_content().get("storage_chat_id") or context.bot_data.get("storage")
    if not chat:
        raise RuntimeError("storage chat not set")
    png = await asyncio.to_thread(engine.render_board, pos)
    m = await context.bot.send_photo(chat, png)
    fid = m.photo[-1].file_id
    try:
        await m.delete()
    except Exception:
        pass
    return fid


async def on_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    mid = q.inline_message_id
    if not mid:
        return await q.answer("این بازی رو از طریق ارسال اینلاین بفرست.", show_alert=True)
    kind, act = q.data.split(":", 1)
    games = context.bot_data.setdefault("games", {})
    u, name = q.from_user, q.from_user.first_name
    if act == "noop":
        return await q.answer()
    try:
        if kind == "sn":
            await snakes_cb(context, q, games, mid, act, u, name)
        else:
            await xo_cb(context, q, games, mid, int(act), u, name)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            log.exception("خطا در بازی")


async def snakes_cb(context, q, games, mid, act, u, name):
    g = games.get(mid)
    if act == "join":
        g = games.setdefault(mid, engine.sn_new())
        if g["started"]:
            return await q.answer("بازی شروع شده.", show_alert=True)
        if any(p[0] == u.id for p in g["players"]):
            return await q.answer("تو قبلاً پیوستی ✅")
        if len(g["players"]) >= 5:
            return await q.answer("ظرفیت پر شده.", show_alert=True)
        g["players"].append((u.id, name))
    elif not g:
        return await q.answer("این بازی منقضی شده. یه بازی جدید بفرست.", show_alert=True)
    elif act == "start":
        if u.id != g["players"][0][0]:
            return await q.answer("فقط میزبان می‌تونه شروع کنه.", show_alert=True)
        if len(g["players"]) < 2:
            return await q.answer("حداقل ۲ نفر لازمه.", show_alert=True)
        g["started"], g["pos"] = True, [0] * len(g["players"])
    elif act == "roll":
        if not g["started"] or g["win"] >= 0:
            return await q.answer()
        if u.id != g["players"][g["T"]][0]:
            return await q.answer("نوبت تو نیست 😅")
        engine.sn_roll(g)
    await q.answer()
    cap, kb = engine.sn_caption(g), sn_kb(g)
    if g["started"]:
        try:
            fid = await board_file_id(context, g["pos"])
            return await context.bot.edit_message_media(
                inline_message_id=mid, media=InputMediaPhoto(fid, caption=cap, parse_mode="HTML"), reply_markup=kb)
        except BadRequest:
            raise
        except Exception:
            log.warning("تصویر ساخته نشد؛ فقط متن به‌روز می‌شود")
    await context.bot.edit_message_caption(inline_message_id=mid, caption=cap, parse_mode="HTML", reply_markup=kb)


async def xo_cb(context, q, games, mid, cell, u, name):
    g = games.setdefault(mid, engine.xo_new())
    if g["res"] or g["b"][cell]:
        return await q.answer()
    idx = g["n"] % 2
    if len(g["p"]) <= idx:
        if any(p[0] == u.id for p in g["p"]):
            return await q.answer("منتظر حریف باش 😉")
        g["p"].append((u.id, name))
    elif g["p"][idx][0] != u.id:
        return await q.answer("نوبت تو نیست 😅")
    g["b"][cell] = "X" if idx == 0 else "O"
    g["n"] += 1
    g["res"] = engine.xo_result(g["b"])
    await q.answer()
    await context.bot.edit_message_text(
        inline_message_id=mid, text=engine.xo_text(g), parse_mode="HTML", reply_markup=xo_kb(g))


async def run():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler(["start", "menu"], send_home))
    app.add_handler(CommandHandler("game", game_cmd))
    app.add_handler(CommandHandler("game", game_cmd))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(CallbackQueryHandler(on_game, pattern=r"^(sn|xo):"))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, send_home))

    # RUN_SECONDS: برای GitHub Actions. بعد از این مدت ربات خاموش می‌شود
    # و اجرای بعدی workflow کار را ادامه می‌دهد. اگر تنظیم نشود، دائمی اجرا می‌شود.
    run_seconds = int(os.environ.get("RUN_SECONDS", "0"))

    async with app:
        await app.start()
        await app.updater.start_polling()
        log.info("ربات روشن شد.")
        if run_seconds > 0:
            await asyncio.sleep(run_seconds)
            log.info("زمان اجرا تمام شد، خاموش می‌شوم تا اجرای بعدی ادامه دهد.")
        else:
            await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    asyncio.run(run())
