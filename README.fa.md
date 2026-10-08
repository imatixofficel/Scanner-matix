# Matix Scanner — اسکنر چندمنبعی IP

نسخه 4 با تمرکز روی منابع معتبر و تست واقعی TCP + TLS + HTTP ساخته شده است.

منابع: ⚡ Fastly · ☁️ Cloudflare · 🟧 CloudFront · 🔷 Google (رنج‌های رسمی؛ کاربر در صفحه وب منبع را انتخاب می‌کند)  
Railway: فقط hostname رسمی و بدون ادعای رنج ثابت عمومی  
VPS: فقط IPهای دستی داخل `custom_ips.txt`

اجرای GitHub Actions هر 15 دقیقه انجام می‌شود و از `workflow_dispatch` برای انتخاب منبع و تعداد IP نیز پشتیبانی می‌کند.

> توجه: IP آنلاین الزاماً VPN endpoint نیست؛ برای VLESS/Trojan/WireGuard باید سرویس مقصد و SNI/Host مناسب وجود داشته باشد.

**نسخه 4.1:** فقط `data/clean_ips.json` لازم است؛ IPهای پین‌شده (`trusted_ips.txt`) و برندگان قبلی در هر اسکن دوباره تست می‌شوند و پاسخ هر IP باید اثبات CDN (`cf-ray` / `x-served-by`) داشته باشد.

اسکنر ترمینال: `python matix.py` (در ویندوز فقط `matix`). گزینه `--diverse` بهترین IP از لوکیشن‌های مختلف دنیا را برمی‌گرداند.

نصب با یک دستور: `pip install https://github.com/imatixofficel/Scanner-matix/archive/refs/heads/main.zip` و بعد فقط `matix` (آپدیت: همان دستور با `--upgrade`).
