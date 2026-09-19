# Matix

Matix is a static, no-build web tool with two parts:

1. **IP Scanner** — pulls the real, official Cloudflare IPv4 ranges from
   [cloudflare.com/ips](https://www.cloudflare.com/ips/) and picks real
   addresses out of those ranges. Actual latency measurement requires a
   backend (see below) — Matix never invents ping, status, or latency
   numbers.
2. **Config Builder** — takes a list of VLESS configs and a list of IP
   addresses and produces every config × IP combination, replacing only the
   address portion of each config and leaving UUID, port, protocol,
   security, SNI, path, fragment, and all other query parameters untouched.

Matix is an independent project. It is inspired by Cloudflare's visual
language but is **not affiliated with or an official product of
Cloudflare**.

## Project structure

```
Matix/
├── index.html
├── style.css
├── app.js
├── worker.js   (optional companion backend — see below)
├── logo.png
└── README.md
```

## Branding

- **Logo**: `logo.png` — a circular purple-and-white badge, used as the
  favicon and throughout the header, drawer, and loading screen.
- **Colors**: a purple/white palette (`--accent: #7C3AED`) defined as CSS
  variables at the top of `style.css` — change them there to re-theme the
  whole site.
- **Fonts**: [Vazirmatn](https://fonts.google.com/specimen/Vazirmatn) for
  Persian/body text (a widely used modern Persian webfont) paired with
  [Manrope](https://fonts.google.com/specimen/Manrope) for the brand name,
  buttons, and data (IP addresses, numbers). Both load from Google Fonts in
  `index.html`. Swap the `<link>` and the `--font-body` / `--font-ui`
  variables in `style.css` if you'd rather use a different Persian font.
- **Loading screen**: shows "به نام خدا", the logo with a soft glow, and the
  word **Matix** filling in with a purple gradient, then fades into the app.

No `npm install`, no bundler, no framework, no database. Every path is
relative, so it runs as-is from any static host, including GitHub Pages.

## Why real ping data needs a backend

GitHub Pages only serves static files — a browser tab cannot open a raw TCP
or ICMP connection to test latency to an arbitrary IP. So Matix's frontend
never fakes this. Instead:

- On **Start Scan**, Matix fetches the official IPv4 ranges directly from
  Cloudflare and randomly samples real addresses from those ranges.
- If no measurement API is configured, the UI tells the user plainly:
  *"اسکنر واقعی هنوز به API متصل نشده است."* (“The real scanner isn’t
  connected to an API yet.”) — instead of showing made-up ping numbers.
- If a measurement API **is** configured, Matix sends it the sampled IPs and
  renders whatever real results come back, sorted by latency.

## Fastest path: deploy the included `worker.js` (no coding required)

`worker.js` is a ready-to-use Cloudflare Worker that solves **both** the
CORS problem for fetching the IP list *and* provides real latency
measurement, using only Cloudflare's own free tier.

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com) → **Workers &
   Pages** → **Create** → **Create Worker**.
2. Give it a name (e.g. `matix-worker`) and click **Deploy** to scaffold it.
3. Click **Edit code**, delete the placeholder, paste in the full contents
   of `worker.js`, then click **Deploy** again.
4. Copy the Worker's URL — it looks like
   `https://matix-worker.YOURNAME.workers.dev`.
5. Open `app.js` and set:

   ```js
   var RANGES_API_URL = 'https://matix-worker.YOURNAME.workers.dev/ranges';
   var SCAN_API_URL    = 'https://matix-worker.YOURNAME.workers.dev/scan';
   ```

6. Re-upload the edited `app.js` to your GitHub repository (same
   drag‑and‑drop upload flow — GitHub will let you overwrite the existing
   file).

That's it — no server to maintain, and everything stays on Cloudflare's free
tier for normal usage volumes.

**One honesty note:** because this Worker itself runs on Cloudflare's
network, the latency it measures reflects edge‑to‑edge routing, not your own
device's last-mile connection. It's still a real, measured value — never a
random or fabricated number — just not identical to what a ping from your
own computer would show.

## Connecting your own measurement backend instead

If you'd rather run your own backend (not the included Worker), open
`app.js` and set:

```js
var SCAN_API_URL = 'https://your-worker-or-backend.example.com/scan';
```

Your endpoint must accept:

```
POST <SCAN_API_URL>
Content-Type: application/json

{ "ips": ["104.16.132.229", "172.67.68.12", "..."] }
```

...and respond with:

```json
{
  "results": [
    { "ip": "104.16.132.229", "ms": 42, "status": "online" },
    { "ip": "172.67.68.12", "ms": null, "status": "offline" }
  ]
}
```

A minimal way to implement this is a small **Cloudflare Worker** (or any
backend) that, for each IP, opens a real connection (e.g. a TCP `connect()`
or an HTTPS request to that IP with the right `Host`/SNI header) and times
the round trip. Keep any API keys or secrets **only** in the
Worker/server's environment variables — never in this frontend, and never
committed to the repository.

### A note on CORS

If `https://www.cloudflare.com/ips-v4` is ever blocked by the browser for
cross-origin requests, Matix reports that honestly (it does not fall back to
a hard-coded or fake IP list). In that case, proxy the request through your
own Worker/backend as well and point the fetch at your proxy instead.

## Deploying to GitHub Pages

1. Create a new GitHub repository (e.g. `matix`).
2. Upload all five files in this folder to the repository root (or to a
   `/docs` folder — either works).
3. In the repository, go to **Settings → Pages**, choose the branch (and
   `/root` or `/docs` folder) to publish from, and save.
4. GitHub will give you a URL like `https://<username>.github.io/matix/` —
   open it once Pages finishes building.
5. (Optional, for real ping data) Deploy a Cloudflare Worker or other
   backend implementing the contract above, then set `SCAN_API_URL` in
   `app.js` to its URL and re-push.

## Config Builder — how address replacement works

Given a VLESS URI:

```
vless://UUID@OLD-ADDRESS:PORT?security=tls&type=ws&path=%2F&host=example.com#remark
```

Matix replaces only `OLD-ADDRESS` with the IP you supply. The UUID, port,
protocol, TLS/security settings, SNI, path, fragment, and every other query
parameter are copied through unchanged. The `host` query parameter (used for
some transports) is left as-is unless it actually contained the address
being replaced.

With **5** configs and **10** IPs, Combine Configs produces **50** outputs,
ordered config-by-config (all 10 IP variants of config 1, then all 10 IP
variants of config 2, and so on).

## Security

- No API keys, tokens, or secrets are stored in this frontend.
- If you connect a backend that needs credentials, keep them in that
  backend's environment variables only.
