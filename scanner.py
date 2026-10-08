"""
Matix Scanner 4.1 - Multi-source, VPN-oriented IP quality scanner.

Only standard-library modules are used.
The scanner samples small, controlled portions of officially published
network ranges and validates candidates with TCP + TLS + HTTP.

IMPORTANT:
- A successful TLS/HTTP test proves the IP is reachable as a web endpoint.
- It does NOT prove that the IP is a working VLESS/WireGuard/Trojan server.
- CDN IPs (Cloudflare/Fastly/CloudFront) normally need the correct SNI/Host in a VPN config.
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
README_FILE = os.path.join(ROOT, "README.md")
CUSTOM_FILE = os.path.join(ROOT, "custom_ips.txt")
TRUSTED_FILE = os.path.join(ROOT, "trusted_ips.txt")
PORT = 443

MAX_LATENCY_MS = 1000
TCP_TIMEOUT = 2.5
TLS_TIMEOUT = 3.5
HTTP_TIMEOUT = 4.0
PROBES = 2
MAX_WORKERS = 120
PREV_RECHECK = 250  # previous winners that are re-tested on every run
PERSISTENT_COUNT = 5
LONG_TERM_COUNT = 30
MAX_RESULTS = 1500

# Built-in snapshot of the officially published ranges. It is used ONLY when the
# official API cannot be reached (blocked network, outage). Every candidate is
# still verified with a CDN fingerprint, so a stale range simply fails the test.
FALLBACK_RANGES = {
    "cloudflare": [
        "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
        "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
        "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
        "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    ],
    "fastly": [
        "23.235.32.0/20", "43.249.72.0/22", "103.244.50.0/24", "103.245.222.0/23",
        "103.245.224.0/24", "104.156.80.0/20", "140.248.64.0/18", "140.248.128.0/17",
        "146.75.0.0/17", "151.101.0.0/16", "157.52.64.0/18", "167.82.0.0/17",
        "167.82.128.0/20", "167.82.160.0/20", "167.82.224.0/20", "172.111.64.0/18",
        "185.31.16.0/22", "199.27.72.0/21", "199.232.0.0/16",
    ],
}

# IATA-style location codes used by Cloudflare (cf-ray) and Fastly (x-served-by).
COLO_COUNTRY = {
    # North America
    "IAD": "USA", "ATL": "USA", "BOS": "USA", "ORD": "USA", "DFW": "USA", "DEN": "USA",
    "LAX": "USA", "SJC": "USA", "SEA": "USA", "MIA": "USA", "EWR": "USA", "LGA": "USA",
    "JFK": "USA", "PDX": "USA", "PHX": "USA", "SLC": "USA", "MSP": "USA", "DTW": "USA",
    "CLT": "USA", "MCI": "USA", "IAH": "USA", "LAS": "USA", "BNA": "USA", "CMH": "USA",
    "PIT": "USA", "TPA": "USA", "SAN": "USA", "SMF": "USA", "OMA": "USA", "STL": "USA",
    "BUF": "USA", "RIC": "USA", "PHL": "USA", "HNL": "USA", "ANC": "USA", "CHI": "USA",
    "YYZ": "Canada", "YUL": "Canada", "YVR": "Canada", "YYC": "Canada", "YOW": "Canada",
    "MEX": "Mexico", "QRO": "Mexico", "GDL": "Mexico",
    # Europe
    "LHR": "UK", "LON": "UK", "MAN": "UK", "EDI": "UK", "LCY": "UK", "DUB": "Ireland",
    "FRA": "Germany", "HAM": "Germany", "DUS": "Germany", "MUC": "Germany", "BER": "Germany", "TXL": "Germany",
    "AMS": "Netherlands", "CDG": "France", "PAR": "France", "MRS": "France",
    "MAD": "Spain", "BCN": "Spain", "LIS": "Portugal", "MXP": "Italy", "LIN": "Italy",
    "FCO": "Italy", "VIE": "Austria", "ZRH": "Switzerland", "GVA": "Switzerland",
    "ARN": "Sweden", "CPH": "Denmark", "OSL": "Norway", "HEL": "Finland", "BRU": "Belgium",
    "WAW": "Poland", "PRG": "Czechia", "BUD": "Hungary", "OTP": "Romania", "SOF": "Bulgaria",
    "ATH": "Greece", "IST": "Turkey", "KBP": "Ukraine", "RIX": "Latvia", "TLL": "Estonia",
    "VNO": "Lithuania", "LUX": "Luxembourg", "SVO": "Russia", "LED": "Russia",
    # Middle East / Caucasus / Central Asia
    "DXB": "UAE", "AUH": "UAE", "FJR": "UAE", "DOH": "Qatar", "KWI": "Kuwait", "BAH": "Bahrain",
    "MCT": "Oman", "RUH": "Saudi Arabia", "JED": "Saudi Arabia", "TLV": "Israel", "AMM": "Jordan",
    "BEY": "Lebanon", "BGW": "Iraq", "EVN": "Armenia", "TBS": "Georgia", "GYD": "Azerbaijan",
    "ALA": "Kazakhstan", "TAS": "Uzbekistan",
    # Asia / Oceania
    "SIN": "Singapore", "HKG": "Hong Kong", "NRT": "Japan", "HND": "Japan", "KIX": "Japan",
    "ICN": "South Korea", "TPE": "Taiwan", "BOM": "India", "DEL": "India", "MAA": "India",
    "BLR": "India", "HYD": "India", "CCU": "India", "KUL": "Malaysia", "BKK": "Thailand",
    "CGK": "Indonesia", "MNL": "Philippines", "SGN": "Vietnam", "HAN": "Vietnam", "DAC": "Bangladesh",
    "KHI": "Pakistan", "ISB": "Pakistan", "CMB": "Sri Lanka", "KTM": "Nepal",
    "SYD": "Australia", "MEL": "Australia", "PER": "Australia", "BNE": "Australia",
    "ADL": "Australia", "CBR": "Australia", "AKL": "New Zealand",
    # South America / Africa
    "GRU": "Brazil", "GIG": "Brazil", "EZE": "Argentina", "SCL": "Chile", "BOG": "Colombia",
    "LIM": "Peru", "PTY": "Panama", "UIO": "Ecuador", "MVD": "Uruguay",
    "JNB": "South Africa", "CPT": "South Africa", "DUR": "South Africa", "CAI": "Egypt",
    "LOS": "Nigeria", "NBO": "Kenya", "ACC": "Ghana", "CMN": "Morocco", "TUN": "Tunisia",
}

SOURCE_META = {
    "cloudflare": ("☁️", "کلادفلر", "https://www.cloudflare.com"),
    "fastly": ("⚡", "فستلی", "https://www.fastly.com"),
    "cloudfront": ("🟧", "کلودفرانت", "https://aws.amazon.com/cloudfront/"),
    "google": ("🔷", "گوگل", "https://www.google.com"),
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
    "cloudfront": "https://ip-ranges.amazonaws.com/ip-ranges.json",
    "google": "https://www.gstatic.com/ipranges/goog.json",
}

# Sources whose candidates are sampled from officially published CIDR lists.
RANGE_SOURCES = ("fastly", "cloudflare", "cloudfront", "google")

# Share of the total --count budget per source in the "all" mode.
DEFAULT_MIX = {
    "fastly": 0.35,
    "cloudflare": 0.30,
    "cloudfront": 0.15,
    "google": 0.08,
    "railway": 0.02,
    "custom": 0.10,
}

# Built-in default pins (used when trusted_ips.txt is not next to the script,
# e.g. when Matix was installed with pip).
DEFAULT_TRUSTED = [
    ("1.1.1.1", "cloudflare"), ("1.0.0.1", "cloudflare"),
    ("104.16.132.229", "cloudflare"), ("172.67.74.152", "cloudflare"),
    ("151.101.1.140", "fastly"), ("151.101.65.140", "fastly"),
    ("151.101.129.140", "fastly"), ("151.101.193.140", "fastly"),
    ("199.232.69.194", "fastly"),
]

SOURCE_TEST = {
    "cloudflare": ("cloudflare.com", "/cdn-cgi/trace"),
    "fastly": ("www.fastly.com", "/"),
    "cloudfront": ("d111111abcdef8.cloudfront.net", "/"),
    "google": ("www.google.com", "/generate_204"),
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
        headers={"User-Agent": "Matix-Scanner/4.1 (+https://github.com/imatixofficel/Scanner-matix)"},
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


def get_ranges(source: str) -> list[str]:
    """Official ranges first; built-in snapshot (if any) only when the API is unreachable."""
    try:
        data = fetch_json(SOURCE_URLS[source])
        if source == "cloudflare":
            ranges = data.get("result", {}).get("ipv4_cidrs", [])
        elif source == "fastly":
            ranges = data.get("addresses", [])
        elif source == "cloudfront":
            ranges = [p["ip_prefix"] for p in data.get("prefixes", [])
                      if p.get("service") == "CLOUDFRONT" and "ip_prefix" in p]
        else:  # google
            ranges = [p["ipv4Prefix"] for p in data.get("prefixes", []) if "ipv4Prefix" in p]
        if ranges:
            return ranges
    except Exception as exc:  # network blocked, HTTP error, bad JSON ...
        print(f"[WARN] {source}: official range list unavailable ({exc})")
    fallback = FALLBACK_RANGES.get(source, [])
    if fallback:
        print(f"[WARN] {source}: using built-in snapshot")
    return list(fallback)


def get_cloudflare() -> list[str]:
    return get_ranges("cloudflare")


def get_fastly() -> list[str]:
    return get_ranges("fastly")


def resolve_hosts(hosts: tuple[str, ...]) -> list[str]:
    out: set[str] = set()
    for host in hosts:
        try:
            for item in socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM):
                out.add(item[4][0])
        except OSError:
            pass
    return sorted(out)


def parse_ip_file(path: str, pinned: bool = False) -> list[dict[str, Any]]:
    """
    Supported lines:
      1.1.1.1
      1.1.1.1,cloudflare
      1.1.1.1 vps
    Blank lines and # comments are ignored.
    """
    out: list[dict[str, Any]] = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
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
            item: dict[str, Any] = {"ip": ip, "source": source}
            if pinned:
                item["pinned"] = True
            out.append(item)
    return out


def parse_custom_file() -> list[dict[str, Any]]:
    path = CUSTOM_FILE if os.path.exists(CUSTOM_FILE) else os.path.join(os.getcwd(), "custom_ips.txt")
    return parse_ip_file(path)


def parse_trusted_file() -> list[dict[str, Any]]:
    if os.path.exists(TRUSTED_FILE):
        return parse_ip_file(TRUSTED_FILE, pinned=True)
    return [{"ip": ip, "source": src, "pinned": True} for ip, src in DEFAULT_TRUSTED]


def candidates_for(source: str, limit: int) -> list[dict[str, Any]]:
    if source == "custom":
        return parse_custom_file()[:limit]

    if source == "trusted":
        return parse_trusted_file()[:limit]

    if source in RANGE_SOURCES:
        return [{"ip": ip, "source": source} for ip in sample_networks(get_ranges(source), limit)]

    if source == "railway":
        return [{"ip": ip, "source": "railway"} for ip in resolve_hosts(RAILWAY_HOSTS)[:limit]]

    if source == "vps":
        # VPS IPs must be explicitly supplied by the operator in custom_ips.txt.
        return [x for x in parse_custom_file() if x["source"] == "vps"][:limit]

    if source == "all":
        # --count is the TOTAL candidate budget, split by DEFAULT_MIX.
        groups: list[dict[str, Any]] = []
        for name, share in DEFAULT_MIX.items():
            try:
                groups.extend(candidates_for(name, max(1, int(limit * share))))
            except Exception as exc:
                print(f"[WARN] source={name}: {exc}")
        # Fill unused slots (e.g. an empty custom list) from Fastly + Cloudflare.
        missing = limit - len(groups)
        if missing > 0:
            for name, part in (("fastly", (missing + 1) // 2), ("cloudflare", missing // 2)):
                try:
                    if part > 0:
                        groups.extend(candidates_for(name, part))
                except Exception as exc:
                    print(f"[WARN] {name} refill: {exc}")
        return groups[:limit]

    raise ValueError(f"Unknown source: {source}")


def build_candidates(source: str, count: int,
                     previous: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """
    Final candidate list = pinned/trusted IPs + previous winners + fresh samples.
    Order matters: the first entry for an IP wins, so the pinned flag is kept.
    """
    def wanted(src: str) -> bool:
        return source in ("all", src) if source != "trusted" else False

    ordered: list[dict[str, Any]] = []

    # 1) pinned IPs are re-verified on every run.
    for item in parse_trusted_file():
        if source in ("all", "trusted") or item["source"] == source:
            ordered.append(item)

    # 2) previous winners are re-tested so that stability can be measured.
    if previous:
        prev_sorted = sorted(previous, key=lambda r: -int(r.get("online_count", 1)))
        taken = 0
        for r in prev_sorted:
            if taken >= PREV_RECHECK:
                break
            if wanted(r.get("source", "custom")):
                ordered.append({"ip": r["ip"], "source": r.get("source", "custom")})
                taken += 1

    # 3) fresh candidates (skipped for the trusted-only mode).
    if source != "trusted":
        ordered.extend(candidates_for(source, count))

    dedup: dict[str, dict[str, Any]] = {}
    for item in ordered:
        try:
            ip = ipaddress.ip_address(item["ip"])
        except ValueError:
            continue
        # Never scan private/reserved/multicast/documentation addresses.
        if not isinstance(ip, ipaddress.IPv4Address) or not ip.is_global:
            continue
        dedup.setdefault(item["ip"], item)
    return list(dedup.values())


def parse_headers(text: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in text.split("\r\n")[1:]:
        if not line:
            break
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return headers


def http_probe(tls_sock: ssl.SSLSocket, host: str, path: str) -> tuple[bool, str | None, dict[str, str]]:
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "User-Agent: Matix-Scanner/4.1\r\n"
        "Accept: */*\r\n"
        "Connection: close\r\n\r\n"
    ).encode()
    tls_sock.sendall(request)
    data = b""
    deadline = time.monotonic() + HTTP_TIMEOUT
    while len(data) < 8192 and time.monotonic() < deadline:
        try:
            chunk = tls_sock.recv(min(2048, 8192 - len(data)))
        except socket.timeout:
            break
        if not chunk:
            break
        data += chunk
        if b"\r\n\r\n" in data:
            break

    text = data.decode("iso-8859-1", errors="ignore")
    first = text.split("\r\n", 1)[0] if text else ""
    # Any valid HTTP status line proves that the endpoint speaks HTTP.
    valid = bool(re.match(r"^HTTP/\d(?:\.\d)?\s+\d{3}\b", first))
    return valid, first or None, parse_headers(text) if valid else {}


def is_cdn_response(source: str, headers: dict[str, str]) -> bool:
    """
    Confirms that the answer really comes from the CDN the IP is claimed to
    belong to. This rejects ISP/DPI hijacks, captive portals and transparent
    proxies that answer on port 443 with a generic HTTP response.
    """
    if source == "cloudflare":
        return "cf-ray" in headers or headers.get("server", "").lower().startswith("cloudflare")
    if source == "fastly":
        return (
            "x-served-by" in headers
            or "x-fastly-request-id" in headers
            or "fastly" in headers.get("server", "").lower()
            or "varnish" in headers.get("via", "").lower()
        )
    if source == "cloudfront":
        return (
            "x-amz-cf-pop" in headers
            or "cloudfront" in headers.get("server", "").lower()
            or "cloudfront" in headers.get("via", "").lower()
        )
    if source == "google":
        server = headers.get("server", "").lower()
        return server.startswith(("gws", "esf", "gfe", "sffe", "gse", "ucfe", "google frontend"))
    return True


def extract_colo(headers: dict[str, str]) -> str | None:
    pop = headers.get("x-amz-cf-pop", "")
    if pop[:3].isalpha() and len(pop) >= 3:
        return pop[:3].upper()
    ray = headers.get("cf-ray", "")
    if "-" in ray:
        code = ray.rsplit("-", 1)[1].strip().upper()
        if code.isalpha() and 3 <= len(code) <= 4:
            return code
    served = headers.get("x-served-by", "")
    if served:
        last = served.split(",")[-1].strip()
        if "-" in last:
            code = last.rsplit("-", 1)[1].strip().upper()
            if code.isalpha() and 3 <= len(code) <= 4:
                return code
    return None


def colo_country(colo: str | None) -> str | None:
    return COLO_COUNTRY.get(colo or "")


def test_candidate(item: dict[str, Any]) -> dict[str, Any]:
    ip = item["ip"]
    source = item["source"]
    default_host, path = SOURCE_TEST.get(source, (None, "/"))
    host = default_host

    # For custom/VPS IPs we cannot safely invent an SNI/Host. Set TEST_HOST
    # when the endpoint requires a specific SNI/Host; otherwise the IP itself
    # is validated as a plain HTTPS endpoint.
    if source in {"custom", "vps"}:
        host = os.environ.get("TEST_HOST", "").strip() or ip

    needs_cdn_proof = source in RANGE_SOURCES

    samples: list[float] = []
    tls_ok = False
    http_ok = False
    cdn_ok = False
    http_status = None
    colo = None

    for _ in range(PROBES):
        start = time.perf_counter()
        raw = None
        tls = None
        try:
            raw = socket.create_connection((ip, PORT), timeout=TCP_TIMEOUT)
            raw.settimeout(TLS_TIMEOUT)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            tls = ctx.wrap_socket(raw, server_hostname=host or ip)
            tls_ok = True
            if host:
                ok, status_line, headers = http_probe(tls, host, path)
                http_ok = http_ok or ok
                if ok and is_cdn_response(source, headers):
                    cdn_ok = True
                    colo = colo or extract_colo(headers)
                if status_line:
                    http_status = status_line
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
            "source": source, "pinned": bool(item.get("pinned")),
        }

    ms = int(round(statistics.median(samples)))
    online = (
        ms <= MAX_LATENCY_MS
        and tls_ok
        and (http_ok if host else True)
        and (cdn_ok if needs_cdn_proof else True)
    )

    return {
        "ip": ip,
        "ms": ms,
        "status": "online" if online else "offline",
        "tls_ok": tls_ok,
        "http_ok": http_ok if host else None,
        "cdn_verified": cdn_ok if needs_cdn_proof else None,
        "http_status": http_status,
        "colo": colo,
        "country": colo_country(colo),
        "source": source,
        "pinned": bool(item.get("pinned")),
    }


def source_fields(source: str) -> tuple[str, str]:
    meta = SOURCE_META.get(source, SOURCE_META["custom"])
    return meta[0], meta[1]


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
    for s in ("fastly", "cloudflare", "cloudfront", "google", "railway", "vps", "custom"):
        emoji, fa, _ = SOURCE_META[s]
        lines.append(f"| {emoji} {fa} | {counts.get(s, {}).get('online', 0)} | {counts.get(s, {}).get('total', 0)} |")
    lines += [
        "",
        f"- 🕐 آخرین اسکن: `{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`",
        f"- ⚡ سقف latency: `{MAX_LATENCY_MS} ms`",
        "- 🔐 اعتبارسنجی: TCP + TLS + HTTP",
        "- 🌍 منابع: Fastly · Cloudflare · CloudFront · Google (رنج‌های رسمی)",
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
                        choices=["all", "cloudflare", "fastly", "cloudfront", "google", "railway", "vps", "custom", "trusted"])
    parser.add_argument("--count", type=int, default=int(os.getenv("SCAN_COUNT", "600")))
    args = parser.parse_args()

    count = max(1, min(args.count, 5000))
    source = args.source

    print(f"Matix Scanner 4.1 | source={source} | count={count}")

    # Stability is tracked inside clean_ips.json itself (no extra data files):
    # an IP that is online again gets online_count + 1, otherwise it drops out.
    previous_doc = load_json(CLEAN_FILE, {})
    previous = [r for r in previous_doc.get("results", []) if isinstance(r, dict) and r.get("ip")]
    prev_counts = {r["ip"]: int(r.get("online_count", 1)) for r in previous}

    try:
        candidates = build_candidates(source, count, previous)
    except Exception as exc:
        print(f"[ERROR] Candidate collection failed: {exc}")
        return 1

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
                    "source": item["source"], "pinned": bool(item.get("pinned")),
                }
            results.append(result)
            if n % 100 == 0 or n == len(candidates):
                print(f"Progress: {n}/{len(candidates)}")

    online = [r for r in results if r["status"] == "online"]
    online.sort(key=lambda r: (not r.get("pinned"), r["ms"] if r["ms"] is not None else 999999))

    final: list[dict[str, Any]] = []
    for r in online:
        emoji, source_name = source_fields(r["source"])
        seen = prev_counts.get(r["ip"], 0) + 1
        final.append({
            "ip": r["ip"],
            "ms": r["ms"],
            "status": "online",
            "colo": r.get("colo"),
            "country": r.get("country"),
            "source": r["source"],
            "source_emoji": emoji,
            "source_name": source_name,
            "pinned": bool(r.get("pinned")),
            "persistent": seen >= PERSISTENT_COUNT,
            "long_term": seen >= LONG_TERM_COUNT,
            "online_count": seen,
            "tls_ok": bool(r.get("tls_ok")),
            "http_ok": r.get("http_ok"),
            "cdn_verified": r.get("cdn_verified"),
            "http_status": r.get("http_status"),
        })
        if len(final) >= MAX_RESULTS:
            break

    output = {
        "updated": now_ts(),
        "total_tested": len(candidates),
        "online_count": len(final),
        "pinned_count": sum(1 for x in final if x["pinned"]),
        "persistent_count": sum(1 for x in final if x["persistent"]),
        "long_term_count": sum(1 for x in final if x["long_term"]),
        "results": final,
        "source_stats": {
            s: {
                "tested": tested_by_source.get(s, 0),
                "online": sum(1 for x in final if x["source"] == s),
            }
            for s in SOURCE_META
        },
        "scanner": {
            "version": "4.1",
            "max_latency_ms": MAX_LATENCY_MS,
            "probes": PROBES,
            "validation": "TCP+TLS+HTTP+CDN-fingerprint",
            "mix": DEFAULT_MIX,
        },
    }
    save_json(CLEAN_FILE, output)

    update_readme(final, tested_by_source)
    print(f"ONLINE: {len(final)} / {len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
