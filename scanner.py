"""
Matix Scanner - Multi-source, VPN-oriented IP quality scanner.

Only standard-library modules are used.
The scanner samples small, controlled portions of officially published
network ranges and validates candidates with TCP + TLS + HTTP.

IMPORTANT:
- A successful TLS/HTTP test proves the IP is reachable as a web endpoint.
- It does NOT prove that the IP is a working VLESS/WireGuard/Trojan server.
- CDN IPs (Cloudflare/Fastly) normally need the correct SNI/Host in a VPN config.
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import os
import random
import re
import socket
import ssl
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
CLEAN_FILE = os.path.join(DATA_DIR, "clean_ips.json")
ALL_FILE = os.path.join(DATA_DIR, "all_ips.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
README_FILE = os.path.join(ROOT, "README.md")
CUSTOM_FILE = os.path.join(ROOT, "custom_ips.txt")

MAX_LATENCY_MS = 1000
TCP_TIMEOUT = 2.5
TLS_TIMEOUT = 3.5
HTTP_TIMEOUT = 4.0
PROBES = 2
MAX_WORKERS = 120
HISTORY_DAYS = 30
PERSISTENT_COUNT = 5
LONG_TERM_COUNT = 30
MAX_RESULTS = 1500

# Keep Cloudflare small because it is not the primary source for this project.
DEFAULT_SAMPLE_LIMITS = {
    "cloudflare": 80,
    "fastly": 500,
    "railway": 30,
    "custom": 1000,
}

SOURCE_META = {
    "cloudflare": ("☁️", "کلادفلر", "https://www.cloudflare.com"),
    "fastly": ("⚡", "فستلی", "https://www.fastly.com"),
    "railway": ("🖥️", "Railway", "https://railway.com"),
    "vps": ("🛡️", "VPS دستی", ""),
    "custom": ("✍️", "دستی", ""),
}

# Railway does NOT publish a stable public inbound IP range. Therefore the
# railway source below resolves Railway's own public hostnames instead of
# pretending that a third-party range is official.
RAILWAY_HOSTS = (
    "railway.app",
    "www.railway.com",
)

SOURCE_URLS = {
    "cloudflare": "https://api.cloudflare.com/client/v4/ips",
    "fastly": "https://api.fastly.com/public-ip-list",
}

SOURCE_TEST = {
    "cloudflare": ("cloudflare.com", "/cdn-cgi/trace"),
    "fastly": ("www.fastly.com", "/"),
    "railway": ("railway.app", "/"),
    "vps": (None, "/"),
    "custom": (None, "/"),
}


def now_ts() -> int:
    return int(time.time())


def load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return default


def save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def fetch_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Matix-Scanner/4.0 (+https://github.com/imatixofficel/Scanner-matix)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def sample_networks(cidrs: list[str], limit: int) -> list[str]:
    """Randomly sample usable IPv4s from CIDRs without expanding huge ranges."""
    result: set[str] = set()
    networks: list[ipaddress.IPv4Network] = []
    for cidr in cidrs:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            if isinstance(net, ipaddress.IPv4Network):
                networks.append(net)
        except ValueError:
            continue

    if not networks or limit <= 0:
        return []

    # Allocate a fair portion to each network, then fill the remainder.
    per_net = max(1, limit // len(networks))
    for net in networks:
        usable = max(0, net.num_addresses - (2 if net.prefixlen < 31 else 0))
        take = min(per_net, usable)
        if take <= 0:
            continue

        if usable <= take:
            for ip in net.hosts():
                result.add(str(ip))
        else:
            first = int(net.network_address) + 1
            last = int(net.broadcast_address) - 1
            for n in random.sample(range(first, last + 1), take):
                result.add(str(ipaddress.IPv4Address(n)))

    # Fill remaining slots from all networks.
    attempts = 0
    while len(result) < limit and attempts < limit * 20:
        net = random.choice(networks)
        usable = max(0, net.num_addresses - (2 if net.prefixlen < 31 else 0))
        if usable:
            n = random.randint(
                int(net.network_address) + (1 if net.prefixlen < 31 else 0),
                int(net.broadcast_address) - (1 if net.prefixlen < 31 else 0),
            )
            result.add(str(ipaddress.IPv4Address(n)))
        attempts += 1
    return list(result)


def get_cloudflare() -> list[str]:
    data = fetch_json(SOURCE_URLS["cloudflare"])
    return data.get("result", {}).get("ipv4_cidrs", [])


def get_fastly() -> list[str]:
    data = fetch_json(SOURCE_URLS["fastly"])
    return data.get("addresses", [])


def resolve_hosts(hosts: tuple[str, ...]) -> list[str]:
    out: set[str] = set()
    for host in hosts:
        try:
            for item in socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM):
                out.add(item[4][0])
        except OSError:
            pass
    return sorted(out)


def parse_custom_file() -> list[dict[str, str]]:
    """
    Supported:
      1.1.1.1
      1.1.1.1,cloudflare
      1.1.1.1 vps
    Blank lines and # comments are ignored.
    """
    out: list[dict[str, str]] = []
    if not os.path.exists(CUSTOM_FILE):
        return out
    with open(CUSTOM_FILE, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in re.split(r"[,|;\s]+", line) if p.strip()]
            try:
                ip = str(ipaddress.ip_address(parts[0]))
            except ValueError:
                continue
            source = parts[1].lower() if len(parts) > 1 else "custom"
            if source not in SOURCE_META:
                source = "custom"
            out.append({"ip": ip, "source": source})
    return out


def candidates_for(source: str, limit: int) -> list[dict[str, str]]:
    if source == "custom":
        return parse_custom_file()[:limit]

    if source == "cloudflare":
        return [{"ip": ip, "source": "cloudflare"} for ip in sample_networks(get_cloudflare(), limit)]

    if source == "fastly":
        return [{"ip": ip, "source": "fastly"} for ip in sample_networks(get_fastly(), limit)]

    if source == "railway":
        return [{"ip": ip, "source": "railway"} for ip in resolve_hosts(RAILWAY_HOSTS)[:limit]]

    if source == "vps":
        # VPS IPs must be explicitly supplied by the operator in custom_ips.txt.
        return [x for x in parse_custom_file() if x["source"] == "vps"][:limit]

    if source == "all":
        # --count is the TOTAL candidate budget.
        # Fastly gets the largest share; Cloudflare stays deliberately small.
        allocations = {
            "fastly": max(1, int(limit * 0.60)),
            "cloudflare": max(1, int(limit * 0.10)),
            "railway": max(1, int(limit * 0.05)),
            "custom": max(1, limit - int(limit * 0.75)),
        }
        groups = []
        for name, quota in allocations.items():
            try:
                groups.extend(candidates_for(name, quota))
            except Exception as exc:
                print(f"[WARN] source={name}: {exc}")
        # Fill unused slots from Fastly if optional sources have no candidates.
        if len(groups) < limit:
            try:
                groups.extend(candidates_for("fastly", limit - len(groups)))
            except Exception as exc:
                print(f"[WARN] fastly refill: {exc}")
        return groups[:limit]

    raise ValueError(f"Unknown source: {source}")


def http_probe(tls_sock: ssl.SSLSocket, host: str, path: str) -> tuple[bool, str | None, str | None]:
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "User-Agent: Matix-Scanner/4.0\r\n"
        "Accept: */*\r\n"
        "Connection: close\r\n\r\n"
    ).encode()
    tls_sock.sendall(request)
    data = b""
    deadline = time.monotonic() + HTTP_TIMEOUT
    while len(data) < 4096 and time.monotonic() < deadline:
        try:
            chunk = tls_sock.recv(min(1024, 4096 - len(data)))
        except socket.timeout:
            break
        if not chunk:
            break
        data += chunk
        if b"\r\n\r\n" in data:
            break

    text = data.decode("iso-8859-1", errors="ignore")
    first = text.splitlines()[0] if text.splitlines() else ""
    # Any valid HTTP response is evidence that the endpoint is speaking HTTP.
    valid = bool(re.match(r"^HTTP/\d(?:\.\d)?\s+\d{3}\b", first))
    colo = None
    for line in text.splitlines():
        if line.lower().startswith("colo="):
            colo = line.split("=", 1)[1].strip() or None
            break
    return valid, first or None, colo


def test_candidate(item: dict[str, str]) -> dict[str, Any]:
    ip = item["ip"]
    source = item["source"]
    default_host, path = SOURCE_TEST.get(source, (None, "/"))
    host = default_host

    # For custom/VPS IPs we cannot safely invent an SNI/Host. A successful
    # TLS handshake is still useful, but HTTP verification is only performed
    # if TEST_HOST is explicitly configured.
    custom_host = os.environ.get("TEST_HOST", "").strip()
    if source in {"custom", "vps"}:
        # Set TEST_HOST when the endpoint requires a specific SNI/Host.
        # Otherwise validate the IP directly as an HTTPS endpoint.
        host = custom_host or ip

    samples: list[float] = []
    tls_ok = False
    http_ok = False
    http_status = None
    colo = None

    for _ in range(PROBES):
        start = time.perf_counter()
        raw = None
        tls = None
        try:
            raw = socket.create_connection((ip, 443), timeout=TCP_TIMEOUT)
            raw.settimeout(TLS_TIMEOUT)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            sni = host or ip
            tls = ctx.wrap_socket(raw, server_hostname=sni)
            tls_ok = True
            if host:
                ok, status_line, probe_colo = http_probe(tls, host, path)
                http_ok = http_ok or ok
                if status_line:
                    http_status = status_line
                if probe_colo:
                    colo = probe_colo
            elapsed = (time.perf_counter() - start) * 1000
            samples.append(elapsed)
        except (OSError, ssl.SSLError, TimeoutError):
            pass
        finally:
            try:
                if tls:
                    tls.close()
                elif raw:
                    raw.close()
            except OSError:
                pass

    if not samples:
        return {
            "ip": ip, "ms": None, "status": "offline",
            "tls_ok": False, "http_ok": False, "http_status": None,
            "source": source,
        }

    ms = int(round(statistics.median(samples)))
    online = ms <= MAX_LATENCY_MS and tls_ok and (http_ok if host else True)

    return {
        "ip": ip,
        "ms": ms,
        "status": "online" if online else "offline",
        "tls_ok": tls_ok,
        "http_ok": http_ok if host else None,
        "http_status": http_status,
        "colo": colo,
        "source": source,
    }


def source_fields(source: str) -> tuple[str, str]:
    meta = SOURCE_META.get(source, SOURCE_META["custom"])
    return meta[0], meta[1]


def load_history() -> dict[str, Any]:
    return load_json(HISTORY_FILE, {"ips": {}, "last_updated": 0})


def update_history(history: dict[str, Any], online: list[dict[str, Any]]) -> None:
    cutoff = now_ts() - HISTORY_DAYS * 86400
    ips = history.setdefault("ips", {})

    for r in online:
        ip = r["ip"]
        e = ips.setdefault(ip, {
            "first_seen": now_ts(),
            "last_seen": now_ts(),
            "online_count": 0,
            "last_ms": None,
            "source": r["source"],
            "history": [],
        })
        e["last_seen"] = now_ts()
        e["online_count"] = e.get("online_count", 0) + 1
        e["last_ms"] = r["ms"]
        e["source"] = r["source"]
        e.setdefault("history", []).append(now_ts())
        e["history"] = [x for x in e["history"] if x >= cutoff]

    for ip in list(ips):
        e = ips[ip]
        e["online_count"] = len([x for x in e.get("history", []) if x >= cutoff])
        if e.get("last_seen", 0) < cutoff:
            del ips[ip]

    history["last_updated"] = now_ts()


def build_readme_stats(results: list[dict[str, Any]], tested_by_source: dict[str, int]) -> str:
    counts: dict[str, dict[str, int]] = {}
    for name in SOURCE_META:
        counts[name] = {"online": 0, "total": tested_by_source.get(name, 0)}
    for r in results:
        s = r.get("source", "custom")
        counts.setdefault(s, {"online": 0, "total": 0})
        if r.get("status") == "online":
            counts[s]["online"] += 1

    lines = [
        "<!-- AUTO_UPDATE_START -->",
        "### 🤖 Matix Live Status",
        "",
        "| منبع | آنلاین | کل تست‌شده |",
        "|---|---:|---:|",
    ]
    for s in ("fastly", "cloudflare", "railway", "vps", "custom"):
        emoji, fa, _ = SOURCE_META[s]
        lines.append(f"| {emoji} {fa} | {counts.get(s, {}).get('online', 0)} | {counts.get(s, {}).get('total', 0)} |")
    lines += [
        "",
        f"- 🕐 آخرین اسکن: `{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`",
        f"- ⚡ سقف latency: `{MAX_LATENCY_MS} ms`",
        "- 🔐 اعتبارسنجی: TCP + TLS + HTTP",
        "- ☁️ Cloudflare: سهم کم و فقط به‌عنوان منبع فرعی",
        "<!-- AUTO_UPDATE_END -->",
    ]
    return "\n".join(lines)


def update_readme(results: list[dict[str, Any]], tested_by_source: dict[str, int]) -> None:
    start, end = "<!-- AUTO_UPDATE_START -->", "<!-- AUTO_UPDATE_END -->"
    block = build_readme_stats(results, tested_by_source)

    try:
        content = open(README_FILE, "r", encoding="utf-8").read() if os.path.exists(README_FILE) else "# Matix Scanner\n"
        if start in content and end in content:
            content = re.sub(re.escape(start) + r".*?" + re.escape(end), block, content, flags=re.S)
        else:
            content = content.rstrip() + "\n\n" + block + "\n"
        with open(README_FILE, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as exc:
        print(f"[WARN] README update failed: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Matix multi-source IP scanner")
    parser.add_argument("--source", default=os.getenv("SCAN_SOURCE", "all"),
                        choices=["all", "cloudflare", "fastly", "railway", "vps", "custom"])
    parser.add_argument("--count", type=int, default=int(os.getenv("SCAN_COUNT", "600")))
    args = parser.parse_args()

    count = max(1, min(args.count, 5000))
    source = args.source

    print(f"Matix Scanner 4.0 | source={source} | count={count}")
    try:
        candidates = candidates_for(source, count)
    except Exception as exc:
        print(f"[ERROR] Candidate collection failed: {exc}")
        return 1

    # Deduplicate by IP while preserving the first trusted source.
    dedup: dict[str, dict[str, str]] = {}
    for item in candidates:
        try:
            ipaddress.ip_address(item["ip"])
        except ValueError:
            continue
        dedup.setdefault(item["ip"], item)
    candidates = list(dedup.values())

    # Never scan arbitrary private/reserved/multicast/documentation addresses.
    candidates = [
        x for x in candidates
        if isinstance(ipaddress.ip_address(x["ip"]), ipaddress.IPv4Address)
        and ipaddress.ip_address(x["ip"]).is_global
    ]

    print(f"Candidates after validation: {len(candidates)}")

    results: list[dict[str, Any]] = []
    tested_by_source: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(test_candidate, item): item for item in candidates}
        for n, future in enumerate(as_completed(futures), 1):
            item = futures[future]
            tested_by_source[item["source"]] = tested_by_source.get(item["source"], 0) + 1
            try:
                result = future.result()
            except Exception as exc:
                print(f"[WARN] test {item['ip']}: {exc}")
                result = {
                    "ip": item["ip"], "ms": None, "status": "offline",
                    "tls_ok": False, "http_ok": False,
                    "source": item["source"],
                }
            results.append(result)
            if n % 100 == 0 or n == len(candidates):
                print(f"Progress: {n}/{len(candidates)}")

    online = [r for r in results if r["status"] == "online"]
    online.sort(key=lambda r: (r["ms"] if r["ms"] is not None else 999999, -int(r.get("http_ok") is True)))

    history = load_history()
    update_history(history, online)
    save_json(HISTORY_FILE, history)

    # Preserve source identity in historical data. Do not publish stale IPs
    # as "online": only currently verified results enter clean_ips.json.
    final: list[dict[str, Any]] = []
    for r in online:
        e = history["ips"].get(r["ip"], {})
        emoji, source_name = source_fields(r["source"])
        count_seen = int(e.get("online_count", 1))
        final.append({
            "ip": r["ip"],
            "ms": r["ms"],
            "status": "online",
            "colo": r.get("colo") or ("N/A" if r["source"] != "cloudflare" else None),
            "source": r["source"],
            "source_emoji": emoji,
            "source_name": source_name,
            "persistent": count_seen >= PERSISTENT_COUNT,
            "long_term": count_seen >= LONG_TERM_COUNT,
            "online_count": count_seen,
            "tls_ok": bool(r.get("tls_ok")),
            "http_ok": r.get("http_ok"),
            "http_status": r.get("http_status"),
        })
        if len(final) >= MAX_RESULTS:
            break

    output = {
        "updated": now_ts(),
        "total_tested": len(candidates),
        "online_count": len(final),
        "results": final,
        "source_stats": {
            s: {
                "tested": tested_by_source.get(s, 0),
                "online": sum(1 for x in final if x["source"] == s),
            }
            for s in SOURCE_META
        },
        "scanner": {
            "version": "4.0",
            "max_latency_ms": MAX_LATENCY_MS,
            "probes": PROBES,
            "validation": "TCP+TLS+HTTP",
            "cloudflare_policy": "small_secondary_source",
        },
    }
    save_json(CLEAN_FILE, output)

    # all_ips is a compact historical index, not a stale public result list.
    all_data = load_json(ALL_FILE, {"ips": {}, "last_updated": 0})
    all_ips = all_data.setdefault("ips", {})
    for r in online:
        old = all_ips.get(r["ip"], {})
        all_ips[r["ip"]] = {
            **old,
            "last_seen": now_ts(),
            "last_ms": r["ms"],
            "source": r["source"],
            "online_count": history["ips"].get(r["ip"], {}).get("online_count", 1),
        }
    all_data["last_updated"] = now_ts()
    save_json(ALL_FILE, all_data)

    update_readme(final, tested_by_source)
    print(f"ONLINE: {len(final)} / {len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
