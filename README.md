# ربات تلگرام دنیای من

منوی خدمات، آموزشات، استخراج و بازی‌های اینلاین (مارپله، منچ ۲ تا ۵ نفره، دوز). محتوا از `content.json` خوانده می‌شود.

## ساختار فایل‌ها
| فایل | کاربرد |
|---|---|
| `bot.py` | هسته‌ی ربات، منو و کنترل بازی‌ها |
| `engine.py` | منطق بازی‌ها و ساخت تصویر تخته |
| `rewards.py` | موجودی، دعوت و برداشت |
| `admin.py` | پنل مدیریت و آمار |
| `content.json` | متن‌ها و دکمه‌ها (بدون نیاز به ری‌استارت) |
| `board_snakes.jpg`، `board_ludo.jpg`، `coins.png`، `banner.jpg` | تصاویر |
| `ludo_layout.json` | مختصات خونه‌های منچ روی تصویر (اگه تصویر تخته عوض شد، باید دوباره تنظیم بشه) |
| `miner.html` | صفحه‌ی استخراج (مینی‌اپ) |

## اجرای محلی
```bash
pip install -r requirements.txt
export BOT_TOKEN="توکن_ربات"      # ویندوز: set BOT_TOKEN=توکن_ربات
python bot.py
```

## ویرایش محتوا
فقط `content.json` را عوض کن.
- `contact`: دکمه پیام به ادمین
- `url`: دکمه لینک
- `inline`: دکمه ارسال بازی به چت (`snakes`، `ludo` یا `xo`)
- `website_url`: آدرس سایت
- `required_channels`: کانال‌های قفل اجباری

## دیپلوی (GitHub Actions)
فایل `.github/workflows/bot.yml` هر ۳۰ دقیقه ربات را اجرا می‌کند.
- توکن را در Settings ← Secrets and variables ← Actions با نام `BOT_TOKEN` بساز.
- در BotFather حالت Inline را برای ربات فعال کن (برای بازی‌ها لازم است).
