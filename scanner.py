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

SAMPLE_PER_RANGE = 300
TIMEOUT = 3
MAX_WORKERS = 100


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
    while len(out) < count:
        offset = random.randint(1, size - 2) if size > 2 else 0
        out.add(int_to_ip(network + offset))
    return list(out)


def test_ip(ip):
    start = time.time()
    try:
        sock = socket.create_connection((ip, 443), timeout=TIMEOUT)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        tls = ctx.wrap_socket(sock, server_hostname="cloudflare.com")
        tls.close()
        return {"ip": ip, "ms": int((time.time() - start) * 1000), "status": "online"}
    except Exception:
        return {"ip": ip, "ms": None, "status": "offline"}


def main():
    candidates = []
    for cidr in CF_RANGES:
        candidates.extend(sample_from_cidr(cidr, SAMPLE_PER_RANGE))

    print(f"Testing {len(candidates)} IPs...")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(test_ip, ip) for ip in candidates]
        for f in as_completed(futures):
            results.append(f.result())

    online = sorted(
        [r for r in results if r["status"] == "online"],
        key=lambda x: x["ms"]
    )

    os.makedirs("data", exist_ok=True)
    with open("data/clean_ips.json", "w", encoding="utf-8") as f:
        json.dump({
            "updated": int(time.time()),
            "total_tested": len(candidates),
            "online_count": len(online),
            "results": online[:200]
        }, f, ensure_ascii=False, indent=2)

    print(f"Done. {len(online)} online, saved top 200.")


if __name__=="__main__":
    main()
