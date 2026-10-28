"""پاداش: موجودی هر کاربر داخل یک پیام پین‌شده‌ی امضاشده (HMAC) در چت خودش با ربات نگه‌داری می‌شود
و بعد از ری‌استارت از همان پیام برگردانده می‌شود. فهرست کاربران و گروه‌ها در فایل db.json پین‌شده‌ی چت ادمین است."""
import base64
import hashlib
import hmac
import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

from telegram import InlineKeyboardButton as IB
from telegram import InlineKeyboardMarkup as IM
from telegram import InputFile
from telegram.error import BadRequest

log = logging.getLogger("rewards")
TAP, DAILY, REF, MIN_WD, REF_TAPS, NEED_INV = 0.001, 500, 0.5, 5.0, 100, 6
NET = {"TRC20": r"^T[1-9A-HJ-NP-Za-km-z]{33}$", "BEP20": r"^0x[0-9a-fA-F]{40}$", "ERC20": r"^0x[0-9a-fA-F]{40}$"}
cfg = lambda: {}   # توسط bot.py تنظیم می‌شود
joined = None      # async (context, uid) -> کانال‌هایی که عضو نیست
kb = None          # fn(uid) -> کیبورد پایین
DB = {"u": {}, "g": {}, "users": {}, "groups": {}}
ADMIN = {"id": 0}
FAILED = set()
_s = {"dirty": False, "last": None, "loaded": False}
KEY = hashlib.sha256(os.environ.get("BOT_TOKEN", "").encode()).digest()


def touch():
    _s["dirty"] = True


def _conf():
    return int(cfg().get("admin_id") or cfg().get("storage_chat_id") or 0)


def admin_id():
    return _conf() or ADMIN["id"]


def is_admin(u):
    if not u:
        return False
    if _conf():
        return u.id == _conf()
    if u.username and u.username.lower() == cfg()["support"]["contact"].lstrip("@").lower():
        ADMIN["id"] = u.id
        return True
    return False


# ---------- کد امضاشده‌ی حساب ----------
def _sig(raw):
    return hmac.new(KEY, raw, hashlib.sha256).hexdigest()[:20]


def encode(u):
    p = {"b": round(u["bal"], 4), "d": u["day"], "t": u["taps"], "T": u["tot"], "r": u["ref"], "i": u["inv"],
         "p": int(u["paid"]), "n": u["name"][:30], "w": u["pw"], "x": round(u["x"], 3)}
    raw = json.dumps(p, separators=(",", ":"), ensure_ascii=False).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=") + "." + _sig(raw)


def decode(text):
    m = re.findall(r"([A-Za-z0-9_\-]{8,})\.([0-9a-f]{20})", text or "")
    if not m:
        return None
    b, s = m[-1]
    try:
        raw = base64.urlsafe_b64decode(b + "=" * (-len(b) % 4))
        if not hmac.compare_digest(s, _sig(raw)):
            return None
        p = json.loads(raw)
        return {"bal": p["b"], "day": p["d"], "taps": p["t"], "tot": p["T"], "ref": p["r"], "inv": p["i"],
                "paid": bool(p["p"]), "name": p["n"], "pw": p["w"], "x": p["x"], "mid": None}
    except Exception:
        return None


def new_user(name=""):
    return {"bal": 0.0, "day": "", "taps": 0, "tot": 0, "ref": None, "inv": 0, "paid": False,
            "name": name, "pw": 0, "x": 0.0, "mid": None, "fresh": True}


def state_text(u):
    return ("🔐 <b>اطلاعات حساب شما</b>\n⚠️ این پیام رو حذف یا آنپین نکن؛ بعد از هر ری‌استارت ربات، موجودی‌ت از همین پیام برگردونده می‌شه.\n\n"
            f"💰 موجودی: ${u['bal']:.3f}\n👥 دعوت‌های موفق: {u['inv']}\n\n<code>{encode(u)}</code>")


async def ensure(bot, uid, name="", create=True):
    k = str(uid)
    u = DB["u"].get(k)
    if u is None:
        if uid == admin_id() and DB.get("au"):
            u = dict(DB["au"], mid=None)
        else:
            try:
                pm = (await bot.get_chat(uid)).pinned_message
                if pm and pm.text and pm.from_user and pm.from_user.id == bot.id:
                    u = decode(pm.text)
                    if u:
                        u["mid"] = pm.message_id
            except Exception as e:
                log.info("خواندن حساب %s ناموفق: %s", uid, e)
        if u is None:
            if not create:
                return None
            u = new_user(name)
        DB["u"][k] = u
        if k not in DB["users"]:
            DB["users"][k] = 1
            touch()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if u["day"] != day:
        u["day"], u["taps"] = day, 0
    if name:
        u["name"] = name
    return u


async def save_user(bot, uid):
    u = DB["u"].get(str(uid))
    if not u:
        return
    if uid == admin_id():  # حساب ادمین داخل db.json ذخیره می‌شود
        DB["au"] = {k: v for k, v in u.items() if k not in ("mid", "fresh")}
        return touch()
    text = state_text(u)
    try:
        if u.get("mid"):
            try:
                await bot.edit_message_text(text, chat_id=uid, message_id=u["mid"], parse_mode="HTML")
                return FAILED.discard(uid)
            except BadRequest as e:
                if "not modified" in str(e).lower():
                    return FAILED.discard(uid)
                u["mid"] = None
        m = await bot.send_message(uid, text, parse_mode="HTML", disable_notification=True)
        await bot.pin_chat_message(uid, m.message_id, disable_notification=True)
        try:
            await bot.delete_message(uid, m.message_id + 1)
        except Exception:
            pass
        u["mid"] = m.message_id
        FAILED.discard(uid)
    except Exception as e:
        FAILED.add(uid)
        log.warning("ذخیره‌ی حساب %s ناموفق: %s", uid, e)


async def retry(bot):
    for uid in list(FAILED)[:25]:
        await save_user(bot, uid)


async def set_ref(bot, uid, inviter, name=""):
    u = await ensure(bot, uid, name)
    if u.pop("fresh", False) and inviter != uid and not u["ref"] and u["tot"] == 0:
        if await ensure(bot, inviter, create=False):
            u["ref"] = inviter
            await save_user(bot, uid)


def miner_url(uid, bot):
    u = DB["u"].get(str(uid)) or new_user()
    c = cfg()
    q = urlencode({"b": round(u["bal"], 3), "l": max(0, DAILY - u["taps"]), "i": u["inv"], "bot": bot, "id": uid,
                   "sup": c["support"]["contact"].lstrip("@"),
                   "ch": ",".join(x.lstrip("@") for x in c.get("required_channels", []))})
    return f"{c['miner_url']}?{q}"


# ---------- دریافت اطلاعات از مینی‌اپ ----------
async def handle(update, context):
    m = update.message
    try:
        d = json.loads(m.web_app_data.data)
    except Exception:
        return None
    u = await ensure(context.bot, m.from_user.id, m.from_user.first_name)
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
    u["bal"] = round(u["bal"] + t * TAP, 4)
    inv = u["ref"]
    if inv and not u["paid"] and u["tot"] >= REF_TAPS and not await joined(context, uid):
        r = await ensure(context.bot, inv, create=False)
        if r:
            u["paid"] = True
            r["bal"] = round(r["bal"] + REF, 4)
            r["inv"] += 1
            await save_user(context.bot, inv)
            try:
                await context.bot.send_message(
                    inv, f"🎉 یکی از دعوت‌هات فعال شد! +${REF:g}\n👥 دعوت‌های موفق: {r['inv']}/{NEED_INV}",
                    reply_markup=kb(inv) if kb else None)
            except Exception:
                pass
    await save_user(context.bot, uid)
    return f"✅ {t} ضربه ثبت شد (+${t * TAP:.3f})\n💰 موجودی: ${u['bal']:.3f}\n🔋 باتری امروز: {DAILY - u['taps']}"


async def withdraw(context, m, u, d):
    net, addr = d.get("net"), str(d.get("addr", "")).strip()
    try:
        amt = round(float(d.get("amt")), 3)
    except (TypeError, ValueError):
        return "❌ مبلغ نامعتبره."
    if u["inv"] < NEED_INV:
        return f"❌ برای برداشت باید اول {NEED_INV} نفر رو با لینک دعوتت بیاری. الان {u['inv']} نفر دعوت کردی."
    if net not in NET or not re.match(NET[net], addr):
        return "❌ آدرس کیف پول با شبکه‌ی انتخابی نمی‌خونه. دوباره چک کن."
    if amt < MIN_WD:
        return f"❌ حداقل برداشت ${MIN_WD:g} است."
    if amt > u["bal"] + 1e-9:
        return "❌ موجودی کافی نیست."
    if u["pw"]:
        return "⏳ یه درخواست در حال بررسی داری. بعد از نتیجه می‌تونی دوباره درخواست بدی."
    adm = admin_id()
    if not adm:
        return "⚠️ برداشت موقتاً فعال نیست."
    fu = m.from_user
    txt = (f"💸 <b>درخواست برداشت</b>\n👤 {fu.first_name} @{fu.username or '-'} (<code>{fu.id}</code>)\n"
           f"💵 ${amt:g}\n🌐 {net}\n<code>{addr}</code>\n👥 دعوت‌ها: {u['inv']} | قبلاً برداشت: ${u['x']:g}")
    try:
        await context.bot.send_message(adm, txt, parse_mode="HTML", reply_markup=IM([[
            IB("✅ پرداخت شد", callback_data=f"wd:ok:{fu.id}:{amt:g}"),
            IB("❌ رد و برگشت", callback_data=f"wd:no:{fu.id}:{amt:g}")]]))
    except Exception:
        log.exception("ارسال به ادمین ناموفق")
        return "⚠️ ثبت درخواست ناموفق بود. بعداً دوباره امتحان کن."
    u["bal"] = round(u["bal"] - amt, 4)
    u["pw"] = amt
    await save_user(context.bot, fu.id)
    return f"✅ درخواست برداشت ${amt:g} ثبت شد. بعد از بررسی به‌صورت دستی پرداخت می‌شه."


async def on_wd(update, context):
    q = update.callback_query
    _, act, uid, amt = q.data.split(":")
    if not is_admin(q.from_user):
        return await q.answer("فقط ادمین.", show_alert=True)
    uid, amt = int(uid), float(amt)
    u = await ensure(context.bot, uid, create=False)
    if not u or not u["pw"]:
        await q.answer("قبلاً بررسی شده.")
        return await q.edit_message_reply_markup(None)
    if act == "ok":
        u["x"] = round(u["x"] + amt, 3)
        note, tag = f"✅ برداشت ${amt:g} برات پرداخت شد.", "\n\n✅ پرداخت شد"
    else:
        u["bal"] = round(u["bal"] + amt, 4)
        note, tag = f"❌ درخواست برداشت رد شد و ${amt:g} به موجودیت برگشت.", "\n\n❌ رد شد"
    u["pw"] = 0
    await save_user(context.bot, uid)
    await q.answer("ثبت شد")
    await q.edit_message_text(q.message.text_html + tag, parse_mode="HTML", reply_markup=None)
    try:
        await context.bot.send_message(uid, note, reply_markup=kb(uid) if kb else None)
    except Exception:
        pass


# ---------- فایل db.json (فهرست کاربران، گروه‌ها، بازی‌ها) ----------
async def load(bot, chat):
    try:
        pm = (await bot.get_chat(chat)).pinned_message
        if pm and pm.document and pm.document.file_name == "db.json":
            f = await pm.document.get_file()
            d = json.loads(bytes(await f.download_as_bytearray()))
            d.pop("u", None)
            DB.update(d)
            for k in ("g", "users", "groups"):
                DB.setdefault(k, {})
            log.info("db.json خوانده شد: %d کاربر", len(DB["users"]))
    except Exception:
        log.exception("خواندن db.json ناموفق بود")
    _s["loaded"] = True


async def autoload(bot):
    if not _s["loaded"] and admin_id():
        await load(bot, admin_id())


async def save(bot, chat):
    if not _s["dirty"]:
        return
    _s["dirty"] = False
    try:
        data = json.dumps({k: v for k, v in DB.items() if k != "u"}, ensure_ascii=False).encode()
        m = await bot.send_document(chat, InputFile(io.BytesIO(data), "db.json"), caption="🗄 پشتیبان (حذف یا آنپین نکن)", disable_notification=True)
        await bot.pin_chat_message(chat, m.message_id, disable_notification=True)
        for mid in (_s["last"], m.message_id + 1):
            if mid:
                try:
                    await bot.delete_message(chat, mid)
                except Exception:
                    pass
        _s["last"] = m.message_id
    except Exception:
        _s["dirty"] = True
        log.exception("ذخیره‌ی db.json ناموفق بود")
