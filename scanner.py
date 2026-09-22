import json
import socket
import ssl
import time
import random
import os
import datetime
import urllib.request
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# تنظیمات
# ============================================================
CF_RANGES = [
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22",
    "103.31.4.0/22", "141.101.64.0/18", "108.162.192.0/18",
    "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22",
    "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
    "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22"
]

SAMPLE_PER_RANGE = 500
MAX_WORKERS = 200
TIMEOUT_TCP = 3
TIMEOUT_HTTP = 5

# ⚙️ تنظیمات ماندگاری
HISTORY_DAYS = 30
MIN_ONLINE_COUNT = 5
LONG_TERM_COUNT = 50
MAX_RESULTS = 2000

# ============================================================
# فایل‌ها
# ============================================================
ALL_IPS_FILE = "data/all_ips.json"
CLEAN_IPS_FILE = "data/clean_ips.json"
HISTORY_FILE = "data/history.json"


# ============================================================
# 🕐 ساعت مطمئن
# ============================================================
def safe_now():
    """
    زمان فعلی رو برمی‌گردونه.
    اگه ساعت سیستم خراب بود، از HTTP header می‌خونه.
    """
    local_ts = int(time.time())
    year = datetime.datetime.utcfromtimestamp(local_ts).year

    # ✅ اگه سال بین 2024 تا 2030 بود → استفاده کن
    if 2024 <= year <= 2030:
        return local_ts

    print(f"⚠️  System clock is wrong (year={year}) — fetching from internet...")

    # ─── روش ۱: Google ───
    try:
        req = urllib.request.Request("https://www.google.com", method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as resp:
            date_header = resp.headers.get("Date")
            if date_header:
                dt = parsedate_to_datetime(date_header)
                fixed_ts = int(dt.timestamp())
                print(f"✅ Got from Google: {dt}")
                return fixed_ts
    except Exception as e:
        print(f"❌ Google failed: {e}")

    # ─── روش ۲: Cloudflare ───
    try:
        req = urllib.request.Request("https://cloudflare.com", method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as resp:
            date_header = resp.headers.get("Date")
            if date_header:
                dt = parsedate_to_datetime(date_header)
                fixed_ts = int(dt.timestamp())
                print(f"✅ Got from Cloudflare: {dt}")
                return fixed_ts
    except Exception as e:
        print(f"❌ Cloudflare failed: {e}")

    # ─── روش ۳: HTTPBin ───
    try:
        req = urllib.request.Request("https://httpbin.org/headers", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            date_header = resp.headers.get("Date")
            if date_header:
                dt = parsedate_to_datetime(date_header)
                fixed_ts = int(dt.timestamp())
                print(f"✅ Got from HTTPBin: {dt}")
                return fixed_ts
    except Exception as e:
        print(f"❌ HTTPBin failed: {e}")

    # ─── fallback ───
    print(f"🚨 All methods failed — using fallback date")
    return int(datetime.datetime(2025, 6, 15, 12, 0, 0).timestamp())


# ============================================================
# توابع کمکی
# ============================================================
def ip_to_int(ip):
    p = list(map(int, ip.split('.')))
    return (p[0] << 24) | (p[1] << 16) | (p[2] << 8) | p[3]


def int_to_ip(n):
    return f"{(n >> 24) & 255}.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"


def sample_from_cidr(cidr, count):
    base, prefix = cidr.split('/')
    base_int = ip_to_int(base)
    host_bits = 32 - int(prefix)
    size = 2 ** host_bits
    network = base_int & (~(size - 1) & 0xFFFFFFFF)
    out = set()
    max_attempts = count * 3
    attempts = 0
    while len(out) < count and attempts < max_attempts:
        offset = random.randint(1, size - 2) if size > 2 else 0
        out.add(int_to_ip(network + offset))
        attempts += 1
    return list(out)


def test_tcp_tls(ip):
    start = time.time()
    try:
        sock = socket.create_connection((ip, 443), timeout=TIMEOUT_TCP)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        tls = ctx.wrap_socket(sock, server_hostname="cloudflare.com")
        tls.send(b"GET /cdn-cgi/trace HTTP/1.1\r\nHost: cloudflare.com\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n")
        tls.settimeout(TIMEOUT_HTTP)
        response = b""
        try:
            while len(response) < 4096:
                chunk = tls.recv(1024)
                if not chunk:
                    break
                response += chunk
        except socket.timeout:
            pass
        tls.close()
        ms = int((time.time() - start) * 1000)
        response_str = response.decode('utf-8', errors='ignore')
        if "HTTP/" in response_str and "colo=" in response_str:
            colo = "UNK"
            for line in response_str.split('\n'):
                if line.startswith('colo='):
                    colo = line.split('=')[1].strip()
                    break
            return {"ip": ip, "ms": ms, "status": "online", "colo": colo}
        else:
            return {"ip": ip, "ms": ms, "status": "half", "colo": None}
    except Exception:
        return {"ip": ip, "ms": None, "status": "offline", "colo": None}


# ============================================================
# مدیریت فایل‌ها
# ============================================================
def load_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# all_ips.json
# ============================================================
def load_all_ips():
    return load_json_file(ALL_IPS_FILE, {"ips": {}, "last_updated": 0})


def save_all_ips(all_ips_data):
    save_json_file(ALL_IPS_FILE, all_ips_data)


def update_all_ips(all_ips_data, new_results):
    now = safe_now()
    ips = all_ips_data.get("ips", {})

    for r in new_results:
        if r["status"] != "online":
            continue

        ip = r["ip"]

        if ip in ips:
            entry = ips[ip]
            entry["last_seen"] = now
            entry["last_ms"] = r["ms"]
            entry["colo"] = r.get("colo")
            entry["seen_count"] = entry.get("seen_count", 0) + 1
        else:
            ips[ip] = {
                "first_seen": now,
                "last_seen": now,
                "last_ms": r["ms"],
                "colo": r.get("colo"),
                "seen_count": 1,
                "status": "online"
            }

    all_ips_data["ips"] = ips
    all_ips_data["last_updated"] = now
    return all_ips_data


def cleanup_all_ips(all_ips_data, max_days=365):
    now = safe_now()
    cutoff = now - (max_days * 86400)
    ips = all_ips_data.get("ips", {})

    cleaned = {}
    for ip, entry in ips.items():
        if entry.get("last_seen", 0) >= cutoff:
            cleaned[ip] = entry

    all_ips_data["ips"] = cleaned
    return all_ips_data


# ============================================================
# history.json
# ============================================================
def load_history():
    return load_json_file(HISTORY_FILE, {"ips": {}, "last_updated": 0})


def save_history(history):
    save_json_file(HISTORY_FILE, history)


def update_history(history, results):
    now = safe_now()
    cutoff = now - (HISTORY_DAYS * 86400)
    ips = history.get("ips", {})

    for r in results:
        if r["status"] != "online":
            continue

        ip = r["ip"]
        if ip not in ips:
            ips[ip] = {
                "first_seen": now,
                "last_seen": now,
                "online_count": 0,
                "last_ms": None,
                "colo": None,
                "history": []
            }

        entry = ips[ip]
        entry["last_seen"] = now
        entry["online_count"] = entry.get("online_count", 0) + 1
        entry["last_ms"] = r["ms"]
        entry["colo"] = r.get("colo")
        entry["history"].append(now)
        entry["history"] = [t for t in entry["history"] if t > cutoff]

    # پاک کردن IPهای قدیمی
    for ip in list(ips.keys()):
        entry = ips[ip]
        if entry["last_seen"] < cutoff:
            del ips[ip]
        else:
            entry["online_count"] = len(entry["history"])

    history["ips"] = ips
    history["last_updated"] = now
    return history


def get_persistent_ips(history):
    persistent = []
    for ip, entry in history.get("ips", {}).items():
        if entry.get("online_count", 0) >= MIN_ONLINE_COUNT:
            persistent.append({
                "ip": ip,
                "online_count": entry["online_count"],
                "last_ms": entry.get("last_ms"),
                "colo": entry.get("colo"),
                "first_seen": entry.get("first_seen"),
                "last_seen": entry.get("last_seen")
            })
    persistent.sort(key=lambda x: x["online_count"], reverse=True)
    return persistent


def get_long_term_ips(history):
    long_term = []
    for ip, entry in history.get("ips", {}).items():
        if entry.get("online_count", 0) >= LONG_TERM_COUNT:
            long_term.append({
                "ip": ip,
                "online_count": entry["online_count"],
                "last_ms": entry.get("last_ms"),
                "colo": entry.get("colo"),
                "first_seen": entry.get("first_seen"),
                "last_seen": entry.get("last_seen")
            })
    long_term.sort(key=lambda x: x["online_count"], reverse=True)
    return long_term


# ============================================================
# اصلی
# ============================================================
def main():
    print("=" * 60)
    print("Matix Scanner v3 — Daily Refresh + Persistent + No Duplicates")
    print("=" * 60)

    # 🕐 چک ساعت
    now_ts = safe_now()
    print(f"\n🕐 Time check:")
    print(f"   raw time.time()  = {int(time.time())}")
    print(f"   safe_now()       = {now_ts}")
    print(f"   UTC              = {datetime.datetime.utcfromtimestamp(now_ts)}")
    print(f"   Year             = {datetime.datetime.utcfromtimestamp(now_ts).year}")

    # ۱. بارگذاری
    print("\n[1/7] Loading previous data...")
    all_ips_data = load_all_ips()
    history = load_history()
    prev_ip_count = len(all_ips_data.get("ips", {}))
    print(f"      Previous IPs in history: {prev_ip_count}")

    # ۲. تولید لیست
    print(f"\n[2/7] Generating fresh candidate IPs...")
    candidates_set = set()
    for cidr in CF_RANGES:
        candidates_set.update(sample_from_cidr(cidr, SAMPLE_PER_RANGE))
    candidates = list(candidates_set)
    print(f"      Generated {len(candidates)} unique candidates")

    # ۳. تست
    print(f"\n[3/7] Testing {len(candidates)} IPs (TCP+TLS)...")
    start = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(test_tcp_tls, ip) for ip in candidates]
        done = 0
        for f in as_completed(futures):
            results.append(f.result())
            done += 1
            if done % 500 == 0:
                print(f"      Progress: {done}/{len(candidates)} ({done*100//len(candidates)}%)")

    print(f"      Stage 1 complete in {time.time()-start:.1f}s")

    online_1 = [r for r in results if r["status"] == "online"]
    print(f"      Online: {len(online_1)}")

    # ۴. حذف تکراری
    print("\n[4/7] Deduplicating current batch...")
    seen = set()
    online_unique = []
    for r in sorted(online_1, key=lambda x: x["ms"] or 99999):
        if r["ip"] not in seen:
            seen.add(r["ip"])
            online_unique.append(r)
    print(f"      Unique in batch
