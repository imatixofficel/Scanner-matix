# Matix Scanner — Cloudflare IP Scanner

> In the name of God

Find clean, fast Cloudflare IPs — automatically, every 10 minutes.

🌐 Live Demo: [https://imatixofficel.github.io/Scanner-matix/](https://imatixofficel.github.io/Scanner-matix/)

---

## What is this?

Matix Scanner is a simple, free tool that finds working Cloudflare IPs for your VLESS, Trojan, or Shadowsocks configs.

It quietly runs in the background every 10 minutes, tests thousands of IPs with real TCP+TLS handshakes and HTTP requests, checks their real download speed, and keeps only the ones that are actually alive and fast.

No fake data. No duplicates. No API keys. Just clean, tested IPs.

---

## Why use it?

- Real testing — not a random list copied from somewhere else
- Always fresh — updated every 10 minutes, 24/7
- Speed-tested — the top 100 IPs are benchmarked for download speed
- Smart tracking — IPs that stay alive over time get marked as persistent 💎
- Zero duplicates — every IP appears only once
- Free forever — no backend, no server, no cost

---

## How to use it

1. Go to 👉 [https://imatixofficel.github.io/Scanner-matix/](https://imatixofficel.github.io/Scanner-matix/)
2. Click Start Scan
3. Pick how many IPs you want
4. Copy the best ones into your config

That's it.

---

## What you get

Every scan gives you a structured list like this:

`json
{
  "ip": "104.25.195.64",
  "ms": 82,
  "status": "online",
  "colo": "SEA",
  "speed_mbps": 17.55,
  "persistent": false,
  "online_count": 1
}
