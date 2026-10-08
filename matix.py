#!/usr/bin/env python3
"""
Matix Scanner CLI
Run:   python matix.py            (interactive)
       python matix.py --source fastly --count 600 --top 20 --diverse --save ips.txt --yes

Uses only the Python standard library. Results are measured from YOUR network.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import scanner

# --------------------------------------------------------------------------
# Terminal helpers
# --------------------------------------------------------------------------
USE_COLOR = True


def init_terminal() -> None:
    global USE_COLOR
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            handle = k32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            k32.GetConsoleMode(handle, ctypes.byref(mode))
            k32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        USE_COLOR = False


def c(text: str, code: int | str, bold: bool = False) -> str:
    if not USE_COLOR:
        return text
    b = "1;" if bold else ""
    return f"\x1b[{b}38;5;{code}m{text}\x1b[0m"


def dim(text: str) -> str:
    return f"\x1b[2m{text}\x1b[0m" if USE_COLOR else text


LOGO_LETTERS = {
    "M": ["███╗   ███╗", "████╗ ████║", "██╔████╔██║", "██║╚██╔╝██║", "██║ ╚═╝ ██║", "╚═╝     ╚═╝"],
    "A": [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
    "T": ["████████╗", "╚══██╔══╝", "   ██║   ", "   ██║   ", "   ██║   ", "   ╚═╝   "],
    "I": ["██╗", "██║", "██║", "██║", "██║", "╚═╝"],
    "X": ["██╗  ██╗", "╚██╗██╔╝", " ╚███╔╝ ", " ██╔██╗ ", "██╔╝ ██╗", "╚═╝  ╚═╝"],
}
GRADIENT = [93, 99, 105, 141, 147, 183]


def banner() -> None:
    rows = ["".join(LOGO_LETTERS[ch][i] for ch in "MATIX") for i in range(6)]
    print()
    for i, row in enumerate(rows):
        print("  " + c(row, GRADIENT[i], bold=True))
    print()
    print("  " + c("Multi-Source IP Scanner", 183, bold=True) + dim("  •  TCP + TLS + HTTP + CDN proof"))
    print("  " + dim("Fastly · Cloudflare · Trusted pins · Custom  —  measured from your own network"))
    print()


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(c("  ❯ ", 141, bold=True) + prompt + suffix + ": ").strip()
    except EOFError:
        return default
    return value or default


def ask_int(prompt: str, default: int, lo: int = 1, hi: int = 5000) -> int:
    raw = ask(prompt, str(default))
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        return default


def menu(title: str, options: list[tuple[str, str]], default: int = 1) -> str:
    print("  " + c(title, 183, bold=True))
    for i, (_, label) in enumerate(options, 1):
        print(f"    {c(str(i), 141, bold=True)}  {label}")
    while True:
        raw = ask("choose", str(default))
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            print()
            return options[int(raw) - 1][0]


# --------------------------------------------------------------------------
# Scanning
# --------------------------------------------------------------------------
def progress_line(done: int, total: int, online: int, best: int | None, started: float) -> str:
    width = 26
    filled = int(width * done / max(1, total))
    bar = c("█" * filled, 141) + dim("░" * (width - filled))
    elapsed = time.time() - started
    eta = (elapsed / done) * (total - done) if done else 0
    best_txt = f"{best} ms" if best is not None else "—"
    clear = "\r\x1b[2K" if USE_COLOR else "\r"
    return (f"{clear}  {bar} {done}/{total} {int(100 * done / max(1, total)):>3}%  "
            f"online {c(str(online), 82, bold=True)}  best {c(best_txt, 220)}  "
            f"ETA {int(eta // 60)}:{int(eta % 60):02d}")


def run_scan(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = len(candidates)
    results: list[dict[str, Any]] = []
    online = 0
    best: int | None = None
    started = time.time()
    pool = ThreadPoolExecutor(max_workers=scanner.MAX_WORKERS)
    futures = {pool.submit(scanner.test_candidate, item): item for item in candidates}
    try:
        for done, fut in enumerate(as_completed(futures), 1):
            item = futures[fut]
            try:
                r = fut.result()
            except Exception:
                r = {"ip": item["ip"], "ms": None, "status": "offline", "source": item["source"]}
            r["pinned"] = bool(item.get("pinned"))
            results.append(r)
            if r["status"] == "online":
                online += 1
                best = r["ms"] if best is None else min(best, r["ms"])
            sys.stdout.write(progress_line(done, total, online, best, started))
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n  " + c("Stopped — showing what was found so far.", 214))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    print("\n")
    return results


def choose(results: list[dict[str, Any]], top: int, diverse: bool) -> list[dict[str, Any]]:
    online = sorted((r for r in results if r["status"] == "online"), key=lambda r: r["ms"])
    if not diverse:
        return online[:top]
    best: dict[str, dict[str, Any]] = {}
    for r in online:
        best.setdefault(r.get("colo") or r["ip"], r)
    picked = sorted(best.values(), key=lambda r: r["ms"])[:top]
    if len(picked) < top:
        ids = {id(x) for x in picked}
        picked += [r for r in online if id(r) not in ids][: top - len(picked)]
    return picked


def ms_color(ms: int) -> int:
    return 82 if ms < 120 else 148 if ms < 250 else 214 if ms < 500 else 203


def show_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("  " + c("No online IPs found.", 203, bold=True))
        print("  " + dim("Your network may block these CDNs, or every response failed the CDN proof check."))
        print()
        return
    head = f"  {'#':>3}  {'IP':<16} {'Latency':>8}  {'Source':<11} Location"
    print(c(head, 183, bold=True))
    print("  " + dim("─" * (len(head) - 2)))
    for i, r in enumerate(rows, 1):
        src = scanner.SOURCE_META.get(r["source"], scanner.SOURCE_META["custom"])
        name = {"cloudflare": "Cloudflare", "fastly": "Fastly", "railway": "Railway"}.get(r["source"], r["source"].title())
        colo = r.get("colo") or "?"
        country = r.get("country")
        loc = f"{colo} · {country}" if country else colo
        pin = c("*", 220, bold=True) if r.get("pinned") else " "
        ms = r["ms"]
        print(f"  {i:>3}{pin} {r['ip']:<16} {c(f'{ms:>5} ms', ms_color(ms))}  {name:<11} {loc}")
    print()


def summary(results: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    online = [r for r in results if r["status"] == "online"]
    places = {r.get("colo") for r in online if r.get("colo")}
    avg = int(sum(r["ms"] for r in online) / len(online)) if online else 0
    print("  " + c(f"{len(online)} online", 82, bold=True) + dim(f" / {len(results)} tested") +
          dim(f"  •  avg {avg} ms  •  {len(places)} locations") + dim("  •  * = pinned"))
    print()


# --------------------------------------------------------------------------
# Output actions
# --------------------------------------------------------------------------
def copy_to_clipboard(text: str) -> bool:
    cmds = []
    if os.name == "nt":
        cmds = [["clip"]]
    elif sys.platform == "darwin":
        cmds = [["pbcopy"]]
    else:
        cmds = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for cmd in cmds:
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode("ascii"), check=True)
                return True
            except Exception:
                continue
    return False


def save_file(path: str, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(r["ip"] for r in rows) + "\n")
    print("  " + c(f"Saved {len(rows)} IPs → {os.path.abspath(path)}", 82))


# --------------------------------------------------------------------------
# Main flow
# --------------------------------------------------------------------------
def interactive_settings() -> dict[str, Any]:
    source = menu("Source", [
        ("all", "Smart mix   — Fastly 60% · Cloudflare 10% · rest custom/railway  (recommended)"),
        ("fastly", "Fastly      — main source"),
        ("cloudflare", "Cloudflare  — secondary source"),
        ("trusted", "Trusted     — only the pinned IPs from trusted_ips.txt (fast)"),
        ("custom", "Custom      — IPs from custom_ips.txt"),
    ])
    count = 0
    if source not in ("trusted", "custom"):
        count = {"1": 200, "2": 600, "3": 1500}.get(
            menu("How many IPs to test?", [("1", "200   quick"), ("2", "600   balanced"), ("3", "1500  deep")], 2), 600)
    mode = menu("Mode", [
        ("fast", "Fastest       — lowest latency first"),
        ("world", "Worldwide     — best IP from as many different locations as possible"),
    ])
    top = ask_int("How many IPs do you want", 20, 1, 500)
    print()
    return {"source": source, "count": count or 600, "top": top, "diverse": mode == "world"}


def action_loop(results: list[dict[str, Any]], rows: list[dict[str, Any]], top: int, diverse: bool) -> None:
    while True:
        print("  " + c("[c]", 141, True) + " copy   " + c("[s]", 141, True) + " save to file   " +
              c("[n]", 141, True) + " change count   " + c("[q]", 141, True) + " quit")
        choice = ask("action", "q").lower()
        if choice == "c":
            ok = copy_to_clipboard("\n".join(r["ip"] for r in rows))
            print("  " + (c(f"Copied {len(rows)} IPs to clipboard.", 82) if ok else
                          c("No clipboard tool found — use [s] to save instead.", 214)))
        elif choice == "s":
            save_file(ask("file name", "matix_ips.txt"), rows)
        elif choice == "n":
            top = ask_int("How many IPs do you want", top, 1, 500)
            rows = choose(results, top, diverse)
            print()
            show_table(rows)
        else:
            break
        print()


def main() -> int:
    init_terminal()
    p = argparse.ArgumentParser(description="Matix Scanner CLI")
    p.add_argument("--source", choices=["all", "fastly", "cloudflare", "railway", "vps", "custom", "trusted"])
    p.add_argument("--count", type=int, default=600, help="how many IPs to test")
    p.add_argument("--top", type=int, default=20, help="how many IPs to show/save")
    p.add_argument("--diverse", action="store_true", help="spread results across different locations")
    p.add_argument("--save", metavar="FILE", help="save the chosen IPs to FILE")
    p.add_argument("--yes", action="store_true", help="non-interactive: no menus, no prompts")
    p.add_argument("--no-color", action="store_true")
    args = p.parse_args()

    global USE_COLOR
    if args.no_color:
        USE_COLOR = False

    banner()
    if args.source or args.yes:
        cfg = {"source": args.source or "all", "count": args.count, "top": args.top, "diverse": args.diverse}
    else:
        cfg = interactive_settings()

    print("  " + dim(f"Collecting candidates ({cfg['source']})..."))
    try:
        candidates = scanner.build_candidates(cfg["source"], max(1, min(cfg["count"], 5000)))
    except Exception as exc:
        print("  " + c(f"Could not collect candidates: {exc}", 203))
        return 1
    if not candidates:
        print("  " + c("No candidates to test.", 203))
        return 1
    print("  " + dim(f"Testing {len(candidates)} IPs on port 443 ...") + "\n")

    results = run_scan(candidates)
    rows = choose(results, cfg["top"], cfg["diverse"])
    summary(results, rows)
    show_table(rows)

    if args.save and rows:
        save_file(args.save, rows)
    if not (args.yes or args.source):
        action_loop(results, rows, cfg["top"], cfg["diverse"])
    return 0 if rows else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        raise SystemExit(130)
