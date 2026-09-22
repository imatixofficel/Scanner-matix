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
# 🕐 ساعت مطمئن (ضد خرابی)
# ============================================================
def safe_now():
    """
    زمان فعلی رو برمی‌گردونه.
    اگه ساعت سیستم خراب بود (خارج از بازه معقول)، از HTTP header می‌خونه.
    """
    local_ts = int(time.time())
    year = datetime.datetime.utcfromtimestamp(local_ts).year

    # بازه معقول: 2024 تا 2030
    if 2024 <= year <= 2030:
        return local_ts

    print(f"⚠️  ساعت سیستم خراب (year={year}) — تلاش برای دریافت از اینترنت...")

    # روش ۱: گوگل
    try:
        req = urllib.request.Request("https://www.google.com", method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as resp:
            date_header = resp.headers.get("Date")
            if date_header:
                dt = parsedate_to_datetime(date_header)
                fixed_ts = int(dt.timestamp())
                print(f"✅ زمان درست (Google): {fixed_ts} → {dt}")
                return fixed_ts
    except Exception as e:
        print(f"❌ Google failed: {e}")

    # روش ۲: Cloudflare
    try:
        req = urllib.request.Request("https://cloudflare.com", method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as resp:
            date_header = resp.headers.get("Date")
            if date_header:
                dt = parsedate_to_datetime(date_header)
                fixed_ts = int(dt.timestamp())
                print(f"✅ زمان درست (Cloudflare): {fixed_ts} → {dt}")
                return fixed_ts
    except Exception as e:
        print(f"❌ Cloudflare failed: {e}")

    print("⚠️  نتوانستم ساعت درست رو بگیرم — از ساعت سیستم استفاده می‌کنم")
    return local_ts


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

    # 🐛 DEBUG CLOCK
    now_ts = safe_now()
    print(f"\n🕐 Server time check:")
    print(f"   raw time.time()   = {int(time.time())}")
    print(f"   safe_now()        = {now_ts}")
    print(f"   UTC               = {datetime.datetime.utcfromtimestamp(now_ts)}")
    print(f"   Local             = {datetime.datetime.fromtimestamp(now_ts)}")

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
    print(f"      Unique in batch: {len(online_unique)}")

    # ۵. به‌روزرسانی
    print("\n[5/7] Updating all_ips and history...")
    all_ips_data = update_all_ips(all_ips_data, online_unique)
    all_ips_data = cleanup_all_ips(all_ips_data, max_days=365)
    save_all_ips(all_ips_data)
    print(f"      Total historical IPs: {len(all_ips_data['ips'])}")

    history = update_history(history, online_unique)
    save_history(history)
    persistent = get_persistent_ips(history)
    long_term = get_long_term_ips(history)
    print(f"      Persistent IPs (≥{MIN_ONLINE_COUNT}): {len(persistent)}")
    print(f"      Long-term IPs (≥{LONG_TERM_COUNT}): {len(long_term)}")

    # ۶. خروجی نهایی
    print("\n[6/7] Building final output (fresh + old, no duplicates)...")

    fresh_ips = {r["ip"]: r for r in online_unique}

    now = safe_now()
    all_known = all_ips_data.get("ips", {})
    all_candidates = {}

    # IPهای تازه
    for ip, r in fresh_ips.items():
        all_candidates[ip] = {
            "ip": ip,
            "ms": r["ms"],
            "status": "online",
            "colo": r.get("colo"),
            "source": "fresh"
        }

    # IPهای قدیمی
    for ip, entry in all_known.items():
        if ip not in all_candidates:
            last_seen_hours = (now - entry.get("last_seen", 0)) / 3600
            all_candidates[ip] = {
                "ip": ip,
                "ms": entry.get("last_ms"),
                "status": "online",
                "colo": entry.get("colo"),
                "source": "old",
                "last_seen_hours_ago": round(last_seen_hours, 1)
            }

    # ماندگاری
    persistent_map = {p["ip"]: p for p in persistent}
    long_term_map = {l["ip"]: l for l in long_term}

    final_list = []
    for ip, item in all_candidates.items():
        if ip in long_term_map:
            item["persistent"] = True
            item["long_term"] = True
            item["online_count"] = long_term_map[ip]["online_count"]
        elif ip in persistent_map:
            item["persistent"] = True
            item["long_term"] = False
            item["online_count"] = persistent_map[ip]["online_count"]
        else:
            item["persistent"] = False
            item["long_term"] = False
            item["online_count"] = history.get("ips", {}).get(ip, {}).get("online_count", 1)

        final_list.append(item)

    final_list.sort(key=lambda x: (
        not x.get("long_term", False),
        not x.get("persistent", False),
        x.get("ms") or 99999
    ))

    seen = set()
    unique_final = []
    for item in final_list:
        if item["ip"] not in seen:
            seen.add(item["ip"])
            unique_final.append(item)

    final_list = unique_final[:MAX_RESULTS]
    print(f"      Final unique IPs: {len(final_list)}")

    # ۷. ذخیره
    print("\n[7/7] Saving output...")

    output = {
        "updated": safe_now(),   # 🕐 اینجا هم safe_now
        "total_tested": len(candidates),
        "online_count": len([x for x in final_list if x["status"] == "online"]),
        "persistent_count": len(persistent),
        "long_term_count": len(long_term),
        "total_historical": len(all_known),
        "fresh_count": len([x for x in final_list if x.get("source") == "fresh"]),
        "old_count": len([x for x in final_list if x.get("source") == "old"]),
        "results": final_list,
        "long_term_ips": long_term[:50],
        "persistent_ips": persistent[:100]
    }

    save_json_file(CLEAN_IPS_FILE, output)

    print(f"\n✅ Done.")
    print(f"   Fresh IPs today:  {output['fresh_count']}")
    print(f"   Old IPs (still alive): {output['old_count']}")
    print(f"   Persistent:       {output['persistent_count']}")
    print(f"   Long-term:        {output['long_term_count']}")
    print(f"   Total unique:     {len(final_list)}")
    print(f"   Updated (unix):   {output['updated']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
