# Matix — Cloudflare IP Scanner & Config Builder

> In the name of God

A lightweight, no-build web tool for finding clean Cloudflare IPs and generating VLESS configs in bulk.

---

## 🌐 Live Demo

- English: [(https://imatixoffice.github.io/Scanner-matix/](https://imatixofficel.github.io/Scanner-matix/)}
- فارسی: [README.fa.md](README.fa.md)

---

## ✨ Features

- Real IP Scanning — Automatically tests 4500+ Cloudflare IPs every 15 minutes via GitHub Actions using real TCP + TLS handshakes.
- Live Results — Results are stored as JSON and served directly to the frontend.
- Config Builder — Combine multiple VLESS configs with multiple IPs in one click. All UUID, port, TLS, SNI, path, and query parameters remain untouched.
- No Backend Required — Fully static, hosted on GitHub Pages.
- Persian UI — Right-to-left layout with Vazirmatn font.

---

## 🏗 How It Works

1. GitHub Actions runs scanner.py every 15 minutes.
2. The scanner samples ~4500 IPs from the official Cloudflare IPv4 ranges.
3. Each IP is tested with a real TCP + TLS handshake on port 443.
4. The best 200 IPs (sorted by latency) are saved to data/clean_ips.json.
5. The frontend (app.js) fetches this JSON and displays the results.

---

## 📁 Project Structure
