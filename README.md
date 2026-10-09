# Matix Scanner — Multi-Source VPN-Oriented IP Scanner

> بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ 🤍

Matix Scanner یک اسکنر چندمنبعی برای پیدا کردن IPهای **واقعاً قابل‌دسترسی** است.

هدف نسخه 4 این است که از چند منبع رسمی (**Fastly، Cloudflare، CloudFront، Google**) IP جمع کند و کاربر خودش منبع را انتخاب کند.

## منابع

| منبع | وضعیت |
|---|---|
| ⚡ Fastly | رنج رسمی (API خود Fastly) |1
| ☁️ Cloudflare | رنج رسمی (API خود Cloudflare) |
| 🟧 CloudFront (آمازون) | رنج رسمی `ip-ranges.json` با فیلتر `CLOUDFRONT` |
| 🔷 Google | رنج رسمی `goog.json` (درصد IP سالم کمتر است، چون فقط بخشی از رنج وب‌سرور است) |
| 🖥️ Railway | فقط از hostname رسمی resolve می‌شود؛ رنج عمومی ثابت ادعا نمی‌شود |
| 🛡️ VPS / ✍️ Custom | فقط IPهایی که خودت در `custom_ips.txt` وارد می‌کنی |

سهم هر منبع در حالت `all`: Fastly 35٪ · Cloudflare 30٪ · CloudFront 15٪ · Google 8٪ · Custom 10٪ · Railway 2٪ (در `DEFAULT_MIX` داخل `scanner.py` قابل تغییر است).

در صفحه وب، بالای لیست می‌توانی **منبع** را انتخاب کنی (همه / Fastly / Cloudflare / CloudFront / Google / Railway / فقط پین‌شده‌ها). لیست همیشه از **کمترین پینگ** شروع می‌شود.

## تست کیفیت

هر IP فقط وقتی وارد `data/clean_ips.json` می‌شود که:

1. اتصال TCP به پورت 443 برقرار شود.
2. TLS handshake موفق باشد.
3. پاسخ HTTP معتبر دریافت شود و برای Cloudflare/Fastly **اثبات CDN** هم وجود داشته باشد (هدر `cf-ray` یا `x-served-by`)؛ پاسخ‌های جعلی ISP/DPI و پراکسی‌های شفاف رد می‌شوند.
4. latency اندازه‌گیری‌شده حداکثر 1000ms باشد.
5. IP از نوع global IPv4 باشد و private/reserved/documentation نباشد.
6. IP فعلی در همین اجرای اسکن آنلاین باشد؛ IP قدیمی دیگر به‌عنوان `online` منتشر نمی‌شود.

### IPهای پین‌شده و پایدار

- IPهای داخل `trusted_ips.txt` در **هر اسکن** دوباره تست می‌شوند و اگر سالم باشند با 📌 بالای لیست نمایش داده می‌شوند.
- برندگان اسکن قبلی هم دوباره تست می‌شوند. `online_count` یعنی چند اسکن پشت‌سرهم آنلاین بوده (💎 از ۵ اسکن، 👑 از ۳۰ اسکن).
- فقط یک فایل داده لازم است: `data/clean_ips.json` (دیگر `all_ips.json` و `history.json` وجود ندارند).

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
  "country": "USA",
  "pinned": false,
  "source": "fastly",
  "source_emoji": "⚡",
  "source_name": "فستلی",
  "persistent": false,
  "long_term": false,
  "online_count": 1,
  "tls_ok": true,
  "http_ok": true,
  "cdn_verified": true
}
```

## نصب با یک دستور از GitHub (بدون نیاز به دانلود پروژه)

```bash
pip install https://github.com/imatixofficel/Scanner-matix/archive/refs/heads/main.zip
matix
```

- Python 3.9 یا بالاتر لازم است؛ `git` لازم نیست. در ویندوز اگر `pip` شناخته نشد: `py -m pip install ...`
- آپدیت: همان دستور را با `--upgrade` دوباره بزن.
- اگر `matix` شناخته نشد: `python -m matix`
- بدون نصب دائمی: `pipx run --spec https://github.com/imatixofficel/Scanner-matix/archive/refs/heads/main.zip matix`

## اسکنر ترمینال (CMD / PowerShell / Terminal)

```bash
matix                # بعد از نصب با pip
python matix.py      # داخل پوشه پروژه
```

در ویندوز داخل پوشه پروژه فقط `matix` هم کافی است. لوگوی Matix نمایش داده می‌شود و از منو منبع، تعداد تست، حالت (سریع‌ترین / سراسر دنیا) و تعداد IP دلخواه را انتخاب می‌کنی؛ بعد از اسکن می‌توانی کپی یا ذخیره کنی.

```bash
python matix.py --source fastly --count 600 --top 20 --diverse --save ips.txt --yes
```

- `--diverse`: بهترین IP از هر لوکیشن (colo) را برمی‌گرداند تا نتایج از نقاط مختلف دنیا باشند.
- نتیجه روی **شبکه خودت** سنجیده می‌شود، پس از GitHub Actions دقیق‌تر است.
- اگر API رسمی در شبکه‌ات بسته باشد، از یک snapshot داخلی رنج‌ها استفاده می‌شود (باز هم همه چیز با اثبات CDN تأیید می‌شود).

## اجرای دستی GitHub Actions

از مسیر **Actions → Matix Multi-Source IP Scanner → Run workflow** می‌توانی:

- منبع را انتخاب کنی: `all / fastly / cloudflare / cloudfront / google / trusted / railway / vps / custom`
- تعداد IPهای مورد تست را تعیین کنی.

اجرای زمان‌بندی‌شده هر **15 دقیقه** انجام می‌شود.

README در هر اجرا timestamp جدید می‌گیرد تا تغییر repository ثبت شود:

`<!-- AUTO_UPDATE_START -->
### 🤖 Matix Live Status

| منبع | آنلاین | کل تست‌شده |
|---|---:|---:|
| ⚡ فستلی | 32 | 270 |
| ☁️ کلادفلر | 117 | 281 |
| 🟧 کلودفرانت | 33 | 244 |
| 🔷 گوگل | 0 | 0 |
| 🖥️ Railway | 0 | 0 |
| 🛡️ VPS دستی | 0 | 0 |
| ✍️ دستی | 0 | 0 |

- 🕐 آخرین اسکن: `2026-10-09 18:45:59 UTC`
- ⚡ سقف latency: `1000 ms`
- 🔐 اعتبارسنجی: TCP + TLS + HTTP
- 🌍 منابع: Fastly · Cloudflare · CloudFront · Google (رنج‌های رسمی)
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
│   └── clean_ips.json
├── custom_ips.txt
├── trusted_ips.txt
├── pyproject.toml
├── scanner.py
├── matix.py
├── matix.bat
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
| ⚡ فستلی | 32 | 270 |
| ☁️ کلادفلر | 117 | 281 |
| 🟧 کلودفرانت | 33 | 244 |
| 🔷 گوگل | 0 | 0 |
| 🖥️ Railway | 0 | 0 |
| 🛡️ VPS دستی | 0 | 0 |
| ✍️ دستی | 0 | 0 |

- 🕐 آخرین اسکن: `2026-10-09 18:45:59 UTC`
- ⚡ سقف latency: `1000 ms`
- 🔐 اعتبارسنجی: TCP + TLS + HTTP
- 🌍 منابع: Fastly · Cloudflare · CloudFront · Google (رنج‌های رسمی)
<!-- AUTO_UPDATE_END -->

## لینک پروژه

https://imatixofficel.github.io/Scanner-matix/

Built by **Matix**.
