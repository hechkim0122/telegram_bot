"""برنامه‌ی پاداش (تپ + دعوت + برداشت دستی). وضعیت در حافظه است و هر ۶۰ ثانیه
به‌صورت فایل db.json داخل چت ادمین (پیام پین‌شده) ذخیره و موقع شروع از همان خوانده می‌شود."""
import io
import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from telegram import InlineKeyboardButton as IB
from telegram import InlineKeyboardMarkup as IM
from telegram import InputFile

log = logging.getLogger("rewards")
TAP, DAILY, REF, MIN_WD, REF_TAPS = 0.001, 500, 0.5, 5.0, 100
NET = {"TRC20": r"^T[1-9A-HJ-NP-Za-km-z]{33}$", "BEP20": r"^0x[0-9a-fA-F]{40}$", "ERC20": r"^0x[0-9a-fA-F]{40}$"}
cfg = lambda: {}  # توسط bot.py تنظیم می‌شود
joined = None     # async (context, uid) -> کانال‌هایی که عضو نیست
DB = {"u": {}, "w": {}, "n": 0}
dirty, last_msg = False, None


def touch():
    global dirty
    dirty = True


def owner(context):
    v = cfg().get("storage_chat_id") or context.bot_data.get("storage")
    return int(v) if v else None


def user(uid, name=""):
    u = DB["u"].get(str(uid))
    if u is None:
        u = DB["u"][str(uid)] = {"bal": 0.0, "day": "", "taps": 0, "tot": 0, "ref": None, "inv": 0, "paid": False, "name": name}
        touch()
    if name:
        u["name"] = name
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if u["day"] != day:
        u["day"], u["taps"] = day, 0
    return u


def set_ref(uid, inviter, name=""):
    """فقط برای کاربر کاملاً جدید و دعوت‌کننده‌ی موجود"""
    new = str(uid) not in DB["u"]
    u = user(uid, name)
    if new and inviter != uid and str(inviter) in DB["u"]:
        u["ref"] = inviter
        touch()


def miner_url(uid, bot):
    u = user(uid)
    q = urlencode({"b": round(u["bal"], 3), "l": max(0, DAILY - u["taps"]), "i": u["inv"], "bot": bot, "id": uid})
    return f"{cfg()['miner_url']}?{q}"


async def handle(update, context):
    m = update.message
    try:
        d = json.loads(m.web_app_data.data)
    except Exception:
        return None
    u = user(m.from_user.id, m.from_user.first_name)
    if d.get("a") == "sync":
        return await sync(context, m.from_user.id, u, d)
    if d.get("a") == "wd":
        return await withdraw(context, m, u, d)


async def sync(context, uid, u, d):
    try:
        t = int(d.get("t", 0))
    except (TypeError, ValueError):
        t = 0
    t = max(0, min(t, DAILY - u["taps"]))  # سقف روزانه سمت ربات اعمال می‌شود
    u["taps"] += t
    u["tot"] += t
    u["bal"] += t * TAP
    inv = u["ref"]
    if inv and not u["paid"] and u["tot"] >= REF_TAPS and str(inv) in DB["u"] and not await joined(context, uid):
        u["paid"] = True
        r = DB["u"][str(inv)]
        r["bal"] += REF
        r["inv"] += 1
        try:
            await context.bot.send_message(inv, f"🎉 یکی از دعوت‌هات فعال شد! +${REF:g} به موجودیت اضافه شد.")
        except Exception:
            pass
    touch()
    return f"✅ {t} ضربه ثبت شد (+${t * TAP:.3f})\n💰 موجودی: ${u['bal']:.3f}\n🔋 باتری امروز: {DAILY - u['taps']}"


async def withdraw(context, m, u, d):
    net, addr = d.get("net"), str(d.get("addr", "")).strip()
    try:
        amt = round(float(d.get("amt")), 3)
    except (TypeError, ValueError):
        return "❌ مبلغ نامعتبره."
    if net not in NET or not re.match(NET[net], addr):
        return "❌ آدرس کیف پول با شبکه‌ی انتخابی نمی‌خونه. دوباره چک کن."
    if amt < MIN_WD:
        return f"❌ حداقل برداشت ${MIN_WD:g} است."
    if amt > u["bal"] + 1e-9:
        return "❌ موجودی کافی نیست."
    if any(w["uid"] == m.from_user.id and w["st"] == "p" for w in DB["w"].values()):
        return "⏳ یه درخواست در حال بررسی داری. بعد از نتیجه می‌تونی دوباره درخواست بدی."
    adm = owner(context)
    if not adm:
        return "⚠️ برداشت موقتاً فعال نیست."
    DB["n"] += 1
    wid = str(DB["n"])
    fu = m.from_user
    txt = (f"💸 <b>درخواست برداشت #{wid}</b>\n👤 {fu.first_name} @{fu.username or '-'} (<code>{fu.id}</code>)\n"
           f"💵 ${amt}\n🌐 {net}\n<code>{addr}</code>")
    try:
        await context.bot.send_message(adm, txt, parse_mode="HTML", reply_markup=IM(
            [[IB("✅ پرداخت شد", callback_data=f"wd:ok:{wid}"), IB("❌ رد و برگشت", callback_data=f"wd:no:{wid}")]]))
    except Exception:
        log.exception("ارسال به ادمین ناموفق")
        return "⚠️ ثبت درخواست ناموفق بود. بعداً دوباره امتحان کن."
    u["bal"] -= amt
    DB["w"][wid] = {"uid": fu.id, "amt": amt, "net": net, "addr": addr, "st": "p"}
    touch()
    return f"✅ درخواست برداشت ${amt:g} ثبت شد. بعد از بررسی به‌صورت دستی پرداخت می‌شه."


async def on_wd(update, context):
    q = update.callback_query
    _, act, wid = q.data.split(":")
    if q.from_user.id != owner(context):
        return await q.answer("فقط ادمین.", show_alert=True)
    w = DB["w"].get(wid)
    if not w or w["st"] != "p":
        return await q.answer("قبلاً بررسی شده.")
    if act == "ok":
        w["st"], note, tag = "d", f"✅ برداشت ${w['amt']:g} برات پرداخت شد.", "\n\n✅ پرداخت شد"
    else:
        w["st"], note, tag = "r", f"❌ درخواست برداشت رد شد و ${w['amt']:g} به موجودیت برگشت.", "\n\n❌ رد شد"
        user(w["uid"])["bal"] += w["amt"]
    touch()
    await q.answer("ثبت شد")
    await q.edit_message_text(q.message.text_html + tag, parse_mode="HTML")
    try:
        await context.bot.send_message(w["uid"], note)
    except Exception:
        pass


# ---------- ذخیره‌سازی داخل تلگرام ----------
async def load(bot, chat):
    global DB
    try:
        pm = (await bot.get_chat(chat)).pinned_message
        if pm and pm.document and pm.document.file_name == "db.json":
            f = await pm.document.get_file()
            DB = json.loads(bytes(await f.download_as_bytearray()))
            log.info("دیتابیس خوانده شد: %d کاربر", len(DB["u"]))
    except Exception:
        log.exception("خواندن دیتابیس ناموفق بود")


async def save(bot, chat):
    global dirty, last_msg
    if not dirty:
        return
    dirty = False
    try:
        data = json.dumps(DB, ensure_ascii=False).encode()
        m = await bot.send_document(chat, InputFile(io.BytesIO(data), "db.json"), caption="🗄 پشتیبان دیتابیس", disable_notification=True)
        await bot.pin_chat_message(chat, m.message_id, disable_notification=True)
        for mid in (last_msg, m.message_id + 1):  # پیام قبلی و پیام سیستمی «پین شد»
            if mid:
                try:
                    await bot.delete_message(chat, mid)
                except Exception:
                    pass
        last_msg = m.message_id
    except Exception:
        dirty = True
        log.exception("ذخیره‌ی دیتابیس ناموفق بود")
