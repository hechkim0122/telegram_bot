import asyncio
import json
import logging
import os
from pathlib import Path

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Markup
from telegram import Update, WebAppInfo
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

CONTENT_FILE = Path(__file__).with_name("content.json")
WELCOME = "🌍 به «دنیای من» خوش اومدی!\nدنیای سرگرمی و هیجان 🎉\n\nیکی از بخش‌ها رو انتخاب کن:"


def load_content() -> dict:
    # هر بار خوانده می‌شود تا با ویرایش content.json نیازی به ری‌استارت نباشد
    with open(CONTENT_FILE, encoding="utf-8") as f:
        return json.load(f)


def home_markup(data: dict) -> Markup:
    buttons = [Btn(c["title"], callback_data=f"cat:{k}") for k, c in data.items()]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return Markup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME, reply_markup=home_markup(load_content()))


async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "برای دیدن بخش‌ها /start رو بزن 👇", reply_markup=home_markup(load_content())
    )


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = load_content()
    parts = q.data.split(":")

    try:
        if parts[0] == "home":
            await q.edit_message_text(WELCOME, reply_markup=home_markup(data))

        elif parts[0] == "cat":
            key = parts[1]
            cat = data[key]
            rows = [
                [Btn(it["title"], callback_data=f"item:{key}:{i}")]
                for i, it in enumerate(cat["items"])
            ]
            rows.append([Btn("🏠 منوی اصلی", callback_data="home")])
            await q.edit_message_text(cat["title"], reply_markup=Markup(rows))

        elif parts[0] == "item":
            key, idx = parts[1], int(parts[2])
            it = data[key]["items"][idx]
            rows = []
            if it.get("webapp"):
                rows.append([Btn("🎮 اجرای بازی", web_app=WebAppInfo(url=it["webapp"]))])
            if it.get("url"):
                rows.append([Btn("🔗 مشاهده", url=it["url"])])
            if it.get("contact"):
                username = it["contact"].lstrip("@")
                rows.append([Btn("💬 سفارش / پیام به ادمین", url=f"https://t.me/{username}")])
            rows.append([Btn("⬅️ بازگشت", callback_data=f"cat:{key}")])
            await q.edit_message_text(
                f"{it['title']}\n\n{it['text']}", reply_markup=Markup(rows)
            )
    except (KeyError, IndexError, ValueError):
        log.exception("callback نامعتبر: %s", q.data)
        await q.edit_message_text(
            "این بخش پیدا نشد. /start رو بزن.", reply_markup=home_markup(data)
        )


async def run():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler(["start", "menu"], start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback))

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
