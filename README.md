# ربات تلگرام دنیای من

منوی خدمات، آموزشات و بازی. محتوا از `content.json` خوانده می‌شود.

## اجرای محلی
```bash
pip install -r requirements.txt
export BOT_TOKEN="توکن_ربات"      # ویندوز: set BOT_TOKEN=توکن_ربات
python bot.py
```

## ویرایش محتوا
فقط `content.json` را عوض کن (بدون نیاز به ری‌استارت ربات).
- `contact`: دکمه پیام به ادمین
- `url`: دکمه لینک
- `webapp`: اجرای بازی HTML5 داخل تلگرام (آدرس باید https باشد)

## دیپلوی (مثلاً Render)
- Build Command: `pip install -r requirements.txt`
- Start Command: `python bot.py`
- نوع سرویس: Background Worker
- متغیر محیطی: `BOT_TOKEN`
