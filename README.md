# ربات تلگرام دنیای من

منوی خدمات، آموزشات و بازی‌های اینلاین (مارپله و دوز). محتوا از `content.json` خوانده می‌شود.

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
- `inline`: دکمه ارسال بازی به چت (`snakes` یا `xo`)
- `website_url`: آدرس سایت
- `required_channels`: کانال‌های قفل اجباری

## دیپلوی (GitHub Actions)
فایل `.github/workflows/bot.yml` هر ۳۰ دقیقه ربات را اجرا می‌کند.
- توکن را در Settings ← Secrets and variables ← Actions با نام `BOT_TOKEN` بساز.
- در BotFather حالت Inline را برای ربات فعال کن (برای بازی‌ها لازم است).
