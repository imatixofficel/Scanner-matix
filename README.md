# Matix Scanner — Multi-Source VPN-Oriented IP Scanner

> بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ 🤍

Matix Scanner یک اسکنر چندمنبعی برای پیدا کردن IPهای **واقعاً قابل‌دسترسی** است.

هدف نسخه 4 این است که به‌جای تکیه زیاد روی Cloudflare، از منابع معتبرتری مثل **Fastly** استفاده کند و Cloudflare را فقط به‌عنوان منبع فرعی نگه دارد.

## منابع

| منبع | وضعیت |
|---|---|
| ⚡ Fastly | منبع اصلی |
| ☁️ Cloudflare | منبع فرعی با سهم کم |
| 🖥️ Railway | فقط از hostname رسمی resolve می‌شود؛ رنج عمومی ثابت ادعا نمی‌شود |
| 🛡️ VPS | فقط IPهایی که خودت در `custom_ips.txt` وارد می‌کنی |
| ✍️ Custom | لیست دستی |

Fastly فهرست عمومی IPهای خودش را به‌صورت رسمی منتشر می‌کند. Cloudflare نیز رنج‌های رسمی خود را منتشر می‌کند. Railway برای ورودی عمومی یک رنج ثابت رسمی ارائه نمی‌کند، بنابراین پروژه رنج‌های غیررسمی را به‌عنوان Railway قبول نمی‌کند.

## تست کیفیت

هر IP فقط وقتی وارد `data/clean_ips.json` می‌شود که:

1. اتصال TCP به پورت 443 برقرار شود.
2. TLS handshake موفق باشد.
3. در منابعی که hostname معتبر دارند، پاسخ HTTP معتبر دریافت شود.
4. latency اندازه‌گیری‌شده حداکثر 1000ms باشد.
5. IP از نوع global IPv4 باشد و private/reserved/documentation نباشد.
6. IP فعلی در همین اجرای اسکن آنلاین باشد؛ IP قدیمی دیگر به‌عنوان `online` منتشر نمی‌شود.

### نکته مهم برای VPN

`online` بودن یک IP به معنی «سرور VLESS/WireGuard/Trojan بودن» نیست.

برای CDNهایی مثل Cloudflare و Fastly، IP معمولاً یک edge است و استفاده از آن در کانفیگ VPN به **SNI/Host/transport درست** نیاز دارد. این پروژه فقط سلامت شبکه و HTTPS endpoint را تأیید می‌کند.

Latency هم از **GitHub Actions runner** اندازه‌گیری می‌شود، نه از اینترنت موبایل یا سیستم شما؛ بنابراین برای انتخاب نهایی، روی شبکه خودتان هم تست کنید.

## خروجی

هر نتیجه این فیلدها را دارد:

```json
{
  "ip": "1.2.3.4",
  "ms": 120,
  "status": "online",
  "colo": "IAD",
  "source": "fastly",
  "source_emoji": "⚡",
  "source_name": "فستلی",
  "persistent": false,
  "long_term": false,
  "online_count": 1,
  "tls_ok": true,
  "http_ok": true
}
```

## اجرای دستی GitHub Actions

از مسیر **Actions → Matix Multi-Source IP Scanner → Run workflow** می‌توانی:

- منبع را انتخاب کنی: `all / fastly / cloudflare / railway / vps / custom`
- تعداد IPهای مورد تست را تعیین کنی.

اجرای زمان‌بندی‌شده هر **15 دقیقه** انجام می‌شود.

README در هر اجرا timestamp جدید می‌گیرد تا تغییر repository ثبت شود:

`<!-- AUTO_UPDATE_START -->
### 🤖 Matix Live Status

| منبع | آنلاین | کل تست‌شده |
|---|---:|---:|
| ⚡ فستلی | 70 | 532 |
| ☁️ کلادفلر | 12 | 61 |
| 🖥️ Railway | 3 | 3 |
| 🛡️ VPS دستی | 0 | 0 |
| ✍️ دستی | 0 | 0 |

- 🕐 آخرین اسکن: `2026-10-08 11:11:55 UTC`
- ⚡ سقف latency: `1000 ms`
- 🔐 اعتبارسنجی: TCP + TLS + HTTP
- ☁️ Cloudflare: سهم کم و فقط به‌عنوان منبع فرعی
<!-- AUTO_UPDATE_END -->`

## custom_ips.txt

فرمت‌ها:

```text
1.1.1.1,cloudflare
8.8.8.8,custom
1.2.3.4,vps
```

فقط IPهایی را وارد کن که مجاز به تست و استفاده از آن‌ها هستی.

## نصب

Python 3.11 کافی است و هیچ package خارجی لازم نیست:

```bash
python scanner.py --source all --count 600
```

یا:

```bash
python scanner.py --source fastly --count 500
```

## ساختار

```text
Scanner-matix/
├── .github/workflows/scan.yml
├── data/
│   ├── clean_ips.json
│   ├── all_ips.json
│   └── history.json
├── custom_ips.txt
├── scanner.py
├── app.js
├── index.html
├── style.css
├── requirements.txt
└── README.md
```

<!-- AUTO_UPDATE_START -->
### 🤖 Matix Live Status

| منبع | آنلاین | کل تست‌شده |
|---|---:|---:|
| ⚡ فستلی | 70 | 532 |
| ☁️ کلادفلر | 12 | 61 |
| 🖥️ Railway | 3 | 3 |
| 🛡️ VPS دستی | 0 | 0 |
| ✍️ دستی | 0 | 0 |

- 🕐 آخرین اسکن: `2026-10-08 11:11:55 UTC`
- ⚡ سقف latency: `1000 ms`
- 🔐 اعتبارسنجی: TCP + TLS + HTTP
- ☁️ Cloudflare: سهم کم و فقط به‌عنوان منبع فرعی
<!-- AUTO_UPDATE_END -->

## لینک پروژه

https://imatixofficel.github.io/Scanner-matix/

Built by **Matix**.
