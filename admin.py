"""پنل مدیریت: ارسال هر پیام (با دکمه) به گروه/کانال و تبلیغ برای همه‌ی کاربران"""
import asyncio
import html
import logging
import re
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton as _B
from telegram import InlineKeyboardMarkup as IM
from telegram.error import RetryAfter
from telegram.ext import ApplicationHandlerStop

import rewards

log = logging.getLogger("admin")


def B(text, style=None, **kw):
    if style:
        kw["api_kwargs"] = {"style": style}
    return _B(text, **kw)


def panel_markup():
    return IM([
        [B("📣 ارسال پیام به گروه یا کانال", "primary", callback_data="adm:grp")],
        [B("📢 تبلیغ برای همه‌ی کاربران", "success", callback_data="adm:t:users")],
        [B("🔎 جستجوی کاربر", "primary", callback_data="adm:find"), B("📊 آمار", callback_data="adm:stat")],
    ])


def stats_text():
    D = rewards.DB
    st = D.get("st", {})
    today = datetime.now(timezone.utc).date()
    dates = [v for v in D["users"].values() if isinstance(v, str)]
    n_today = sum(1 for d in dates if d == today.isoformat())
    n_week = sum(1 for d in dates if d >= (today - timedelta(days=6)).isoformat())
    pend = max(0, int(st.get("wd_req", 0) - st.get("paid_n", 0) - st.get("rej_n", 0)))
    return ("📊 <b>آمار ربات</b>\n━━━━━━━━━━━━\n"
            f"👥 کاربران: <b>{len(D['users'])}</b>\n   • عضو شده‌ی امروز: {n_today}\n   • ۷ روز اخیر: {n_week}\n"
            f"📣 گروه/کانال‌ها: <b>{len(D['groups'])}</b>\n\n"
            f"🎮 بازی‌ها: 🐍 {int(st.get('games_sn', 0))}  |  🎲 {int(st.get('games_ld', 0))}  |  ⭕ {int(st.get('games_xo', 0))}\n"
            f"🕹 بازی‌های فعال (۴۸ ساعت اخیر): {len(D.get('g', {}))}\n\n"
            f"⛏ مجموع ضربه‌ها: {int(st.get('taps', 0)):,}\n"
            f"💸 برداشت‌ها: پرداخت‌شده {int(st.get('paid_n', 0))} (${st.get('paid', 0):g}) • رد‌شده {int(st.get('rej_n', 0))} • در انتظار {pend}")


async def user_card(context, uid):
    u = await rewards.ensure(context.bot, uid, create=False)
    if not u:
        return None
    ref = f"<code>{u['ref']}</code>" if u["ref"] else "-"
    return (f"👤 <b>{html.escape(u['name'] or '-')}</b> (<code>{uid}</code>)\n"
            f"💰 موجودی: ${u['bal']:.3f}\n👥 دعوت‌های موفق: {u['inv']}\n⛏ مجموع ضربه‌ها: {u['tot']}\n"
            f"💸 برداشت‌شده: ${u['x']:g}" + (f"\n⏳ درخواست باز: ${u['pw']:g}" if u["pw"] else "")
            + f"\n🔗 دعوت‌کننده: {ref}")


async def panel_cmd(update, context):
    if not rewards.is_admin(update.effective_user):
        return
    context.user_data.pop("adm", None)
    await update.effective_message.reply_text("🛠 <b>پنل مدیریت</b>", parse_mode="HTML", reply_markup=panel_markup())


def parse_btns(text):
    """هر خط یک ردیف: «متن | لینک». چند دکمه در یک ردیف: با && جدا کن."""
    rows = []
    for line in text.splitlines():
        row = []
        for part in line.split("&&"):
            if "|" not in part:
                continue
            t, u = [x.strip() for x in part.split("|", 1)]
            if u.startswith("@"):
                u = "https://t.me/" + u[1:]
            elif u.lower().startswith(("t.me/", "www.")):
                u = "https://" + u
            if not t or not re.match(r"^https?://\S+$", u):
                raise ValueError(part)
            row.append(_B(t, url=u))
        if row:
            rows.append(row)
    if not rows:
        raise ValueError("empty")
    return rows


def target_name(t):
    return f"همه‌ی کاربران ({len(rewards.DB['users'])} نفر)" if t == "users" else rewards.DB["groups"].get(str(t), str(t))


async def preview(update, context):
    a = context.user_data["adm"]
    chat, mid = a["src"]
    mk = IM(a["btns"]) if a.get("btns") else None
    await context.bot.copy_message(update.effective_chat.id, chat, mid, reply_markup=mk)
    await update.effective_message.reply_text(
        f"👆 پیش‌نمایش پیام.\n🎯 هدف: {target_name(a['target'])}\nارسال کنم؟",
        reply_markup=IM([
            [B("✅ ارسال", "success", callback_data="adm:send")],
            [B("➕ افزودن/تغییر دکمه‌ها", "primary", callback_data="adm:btn")],
            [B("❌ لغو", "danger", callback_data="adm:cancel")],
        ]))


async def msg(update, context):
    """پیام‌های ادمین وقتی تو یکی از مرحله‌های پنل است (قبل از بقیه‌ی هندلرها اجرا می‌شود)"""
    a = context.user_data.get("adm")
    if not a or not update.message or not rewards.is_admin(update.effective_user):
        return
    m, step = update.message, a.get("step")
    if step == "add":
        t = (m.text or "").strip()
        t = re.sub(r"^https?://t\.me/", "@", t)
        try:
            ch = await context.bot.get_chat(int(t) if re.fullmatch(r"-?\d+", t) else t)
        except Exception:
            await m.reply_text("❌ این چت پیدا نشد. مطمئن شو ربات عضو (یا ادمین) اونه و آیدی رو درست فرستادی.")
            raise ApplicationHandlerStop
        rewards.DB["groups"][str(ch.id)] = ch.title or str(ch.id)
        rewards.touch()
        context.user_data.pop("adm")
        await m.reply_text(f"✅ «{ch.title}» اضافه شد.", reply_markup=panel_markup())
        raise ApplicationHandlerStop
    if step == "find":
        t = (m.text or "").strip()
        card = await user_card(context, int(t)) if t.isdigit() else None
        if card:
            context.user_data.pop("adm", None)
            await m.reply_text(card, parse_mode="HTML", reply_markup=panel_markup())
        else:
            await m.reply_text("❌ کاربری با این آیدی عددی پیدا نشد. دوباره بفرست یا از پنل لغو کن.",
                               reply_markup=IM([[B("❌ لغو", "danger", callback_data="adm:cancel")]]))
        raise ApplicationHandlerStop
    if step == "msg":
        a["src"], a["step"] = (m.chat_id, m.message_id), "ready"
        await preview(update, context)
        raise ApplicationHandlerStop
    if step == "btn":
        try:
            a["btns"] = parse_btns(m.text or "")
        except ValueError:
            await m.reply_text("❌ فرمت درست نیست. هر خط: متن دکمه | لینک\nمثال:\nکانال ما | https://t.me/donyayeman0122")
            raise ApplicationHandlerStop
        a["step"] = "ready"
        await preview(update, context)
        raise ApplicationHandlerStop


async def cb(update, context):
    q = update.callback_query
    if not rewards.is_admin(q.from_user):
        return await q.answer("فقط ادمین.", show_alert=True)
    await q.answer()
    p = q.data.split(":")
    ud, act = context.user_data, p[1]
    if act == "home" or act == "cancel":
        ud.pop("adm", None)
        await q.edit_message_text("🛠 <b>پنل مدیریت</b>", parse_mode="HTML", reply_markup=panel_markup())
    elif act == "stat":
        try:
            await q.edit_message_text(stats_text(), parse_mode="HTML", reply_markup=IM([
                [B("🔄 تازه‌سازی", "primary", callback_data="adm:stat")], [B("⬅️ بازگشت", callback_data="adm:home")]]))
        except Exception:
            pass  # بدون تغییر
    elif act == "find":
        ud["adm"] = {"step": "find"}
        await q.edit_message_text("آیدی عددی کاربر رو بفرست (مثلاً از پیام درخواست برداشت):",
                                  reply_markup=IM([[B("❌ لغو", "danger", callback_data="adm:cancel")]]))
    elif act == "grp":
        rows = [[B(f"📣 {t}", callback_data=f"adm:t:{cid}")] for cid, t in rewards.DB["groups"].items()]
        rows += [[B("➕ افزودن گروه/کانال", "success", callback_data="adm:add")], [B("⬅️ بازگشت", callback_data="adm:home")]]
        await q.edit_message_text("کدوم گروه یا کانال؟\n(گروه‌هایی که ربات بهشون اضافه بشه خودکار اینجا میان)", reply_markup=IM(rows))
    elif act == "add":
        ud["adm"] = {"step": "add"}
        await q.edit_message_text("@یوزرنیم یا آیدی عددی گروه/کانال رو بفرست (ربات باید عضو یا ادمینش باشه):")
    elif act == "t":
        t = p[2]
        ud["adm"] = {"step": "msg", "target": t}
        await q.edit_message_text(f"🎯 هدف: {target_name(t)}\n\nحالا پیامت رو همین‌جا بفرست (متن، عکس، ویدیو، فایل…). همون رو عیناً می‌فرستم.")
    elif act == "btn" and ud.get("adm"):
        ud["adm"]["step"] = "btn"
        await q.message.reply_text("دکمه‌ها رو بفرست؛ هر خط یک ردیف:\nمتن دکمه | لینک\nچند دکمه در یک ردیف: با && جدا کن.\nمثال:\nکانال ما | https://t.me/donyayeman0122 && پشتیبانی | @hechkim0122")
    elif act == "send" and ud.get("adm", {}).get("src"):
        a = ud.pop("adm")
        await q.edit_message_text("⏳ در حال ارسال…")
        context.application.create_task(deliver(context, q.message.chat_id, a))


async def deliver(context, admin_chat, a):
    chat, mid = a["src"]
    mk = IM(a["btns"]) if a.get("btns") else None
    t = a["target"]
    ids = [int(k) for k in rewards.DB["users"]] if t == "users" else [int(t) if re.fullmatch(r"-?\d+", str(t)) else t]
    ok = bad = 0
    for uid in ids:
        for attempt in (1, 2):
            try:
                await context.bot.copy_message(uid, chat, mid, reply_markup=mk)
                ok += 1
                break
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except Exception as e:
                if attempt == 2 or len(ids) == 1:
                    bad += 1
                    log.info("ارسال به %s ناموفق: %s", uid, e)
                break
        if len(ids) > 1:
            await asyncio.sleep(0.05)
    await context.bot.send_message(admin_chat, f"✅ ارسال شد: {ok}\n❌ ناموفق: {bad}", reply_markup=panel_markup())


async def on_member(update, context):
    cm = update.my_chat_member
    ch = cm.chat
    if ch.type == "private":
        return
    if cm.new_chat_member.status in ("member", "administrator"):
        rewards.DB["groups"][str(ch.id)] = ch.title or str(ch.id)
    elif cm.new_chat_member.status in ("left", "kicked"):
        rewards.DB["groups"].pop(str(ch.id), None)
    rewards.touch()
