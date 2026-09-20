import json
import socket
import ssl
import time
import random
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

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
HISTORY_DAYS = 7
MIN_ONLINE_COUNT = 3

CLEAN_IPS_FILE = "data/clean_ips.json"
HISTORY_FILE = "data/history.json"


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


def test_speed(ip):
    try:
        start = time.time()
        sock = socket.create_connection((ip, 443), timeout=TIMEOUT_TCP)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        tls = ctx.wrap_socket(sock, server_hostname="speed.cloudflare.com")
        tls.send(b"GET /__down?bytes=1000000 HTTP/1.1\r\nHost: speed.cloudflare.com\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n")
        tls.settimeout(10)
        total = 0
        header_end = False
        header_buf = b""
        while True:
            try:
                chunk = tls.recv(16384)
                if not chunk:
                    break
                if not header_end:
                    header_buf += chunk
                    if b"\r\n\r\n" in header_buf:
                        idx = header_buf.index(b"\r\n\r\n") + 4
                        total += len(header_buf) - idx
                        header_end = True
                else:
                    total += len(chunk)
                if total > 1000000:
                    break
            except socket.timeout:
                break
        tls.close()
        elapsed = time.time() - start
        speed_mbps = (total * 8) / (elapsed * 1000000) if elapsed > 0 else 0
        return {"speed_mbps": round(speed_mbps, 2)}
    except Exception:
        return {"speed_mbps": 0}


def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"ips": {}, "last_updated": 0}


def save_history(history):
    os.makedirs("data", exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def update_history(history, results):
    now = time.time()
    cutoff = now - (HISTORY_DAYS * 86400)
    for r in results:
        if r["status"] != "online":
            continue
        ip = r["ip"]
        if ip not in history["ips"]:
            history["ips"][ip] = {
                "first_seen": now, "last_seen": now,
                "online_count": 0, "last_ms": None,
                "colo": None, "history": []
            }
        entry = history["ips"][ip]
        entry["last_seen"] = now
        entry["online_count"] = entry.get("online_count", 0) + 1
        entry["last_ms"] = r["ms"]
        entry["colo"] = r.get("colo")
        entry["history"].append(now)
        entry["history"] = [t for t in entry["history"] if t > cutoff]
    for ip in list(history["ips"].keys()):
        entry = history["ips"][ip]
        if entry["last_seen"] < cutoff:
            del history["ips"][ip]
        else:
            entry["online_count"] = len(entry["history"])
    history["last_updated"] = now
    return history


def get_persistent_ips(history):
    persistent = []
    for ip, entry in history["ips"].items():
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


def main():
    print("=" * 60)
    print("Matix Scanner v2")
    print("=" * 60)
    print("\n[1/6] Generating candidates...")
    candidates_set = set()
    for cidr in CF_RANGES:
        candidates_set.update(sample_from_cidr(cidr, SAMPLE_PER_RANGE))
    candidates = list(candidates_set)
    print(f"      {len(candidates)} unique IPs")

    print(f"\n[2/6] Stage 1: TCP+TLS ({len(candidates)} IPs)...")
    start = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(test_tcp_tls, ip) for ip in candidates]
        done = 0
        for f in as_completed(futures):
            results.append(f.result())
            done += 1
            if done % 500 == 0:
                print(f"      {done}/{len(candidates)} ({done*100//len(candidates)}%)")
    print(f"      Done in {time.time()-start:.1f}s")

    online_1 = [r for r in results if r["status"] == "online"]
    print(f"      Online: {len(online_1)}")

    print("\n[3/6] Deduplicating...")
    seen = set()
    online_unique = []
    for r in sorted(online_1, key=lambda x: x["ms"] or 99999):
        if r["ip"] not in seen:
            seen.add(r["ip"])
            online_unique.append(r)
    print(f"      {len(online_unique)} unique")

    print("\n[4/6] Speed test TOP 100...")
    top_for_speed = online_unique[:100]
    speed_results = {}
    with ThreadPoolExecutor(max_workers=30) as ex:
        futures = {ex.submit(test_speed, r["ip"]): r["ip"] for r in top_for_speed}
        for f in as_completed(futures):
            ip = futures[f]
            try:
                speed_results[ip] = f.result()
            except Exception:
                speed_results[ip] = {"speed_mbps": 0}
    for r in online_unique:
        r["speed_mbps"] = speed_results.get(r["ip"], {}).get("speed_mbps", None)

    online_unique.sort(key=lambda x: (x["ms"] or 99999, -(x.get("speed_mbps") or 0)))

    print("\n[5/6] Updating history...")
    history = load_history()
    history = update_history(history, results)
    persistent = get_persistent_ips(history)
    print(f"      Persistent: {len(persistent)}")
    save_history(history)

    print("\n[6/6] Saving...")
    os.makedirs("data", exist_ok=True)
    persistent_ips = {p["ip"] for p in persistent}
    final_results = []
    for r in online_unique:
        if r["ip"] in persistent_ips:
            r["persistent"] = True
            r["online_count"] = history["ips"][r["ip"]]["online_count"]
            final_results.append(r)
    for r in online_unique:
        if r["ip"] not in persistent_ips:
            r["persistent"] = False
            r["online_count"] = history["ips"].get(r["ip"], {}).get("online_count", 1)
            final_results.append(r)

    output = {
        "updated": int(time.time()),
        "total_tested": len(candidates),
        "online_count": len(online_unique),
        "persistent_count": len(persistent),
        "results": final_results[:1000],
        "persistent_ips": persistent[:100]
    }
    with open(CLEAN_IPS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nDone. {len(final_results[:1000])} IPs saved.")
    print("=" * 60)


if __name__ == "__main__":
    main()
