import asyncio
import json
import logging
import os
import secrets
from pathlib import Path
from urllib.parse import quote

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Markup
from telegram import Update, WebAppInfo
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO
)
log = logging.getLogger("donyaye-man")

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
            [Btn("🌐 وبسایت", url=data["website_url"])],
            [
                Btn(s["services"]["title"], callback_data="cat:services"),
                Btn(s["tutorials"]["title"], callback_data="cat:tutorials"),
                Btn(s["games"]["title"], callback_data="cat:games"),
            ],
            [
                Btn(data["settings"]["title"], callback_data="cat:settings"),
                Btn("💬 پشتیبانی", callback_data="support"),
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
                [Btn("💬 پیام به پشتیبانی", url=tg_link(sup["contact"]))],
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
            if it.get("webapp"):
                rows.append([Btn("🎮 اجرای بازی", web_app=WebAppInfo(url=it["webapp"]))])
            if it.get("url"):
                rows.append([Btn("🔗 مشاهده", url=it["url"])])
            if it.get("contact"):
                rows.append([Btn("💬 سفارش / پیام به ادمین", url=tg_link(it["contact"]))])
            rows.append(back_row(key))
            rows.append(HOME_ROW)
            await show(q, f"{it['title']}\n\n{it['text']}", Markup(rows))

    except (KeyError, IndexError, ValueError):
        log.exception("callback نامعتبر: %s", q.data)
        await show(q, "این بخش پیدا نشد. به منوی اصلی برگرد.", Markup([HOME_ROW]))


async def run():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler(["start", "menu"], send_home))
    app.add_handler(CommandHandler("game", game_cmd))
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
