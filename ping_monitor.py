#!/usr/bin/env python3
"""ping_monitor.py — Terminal network connectivity monitor."""

import argparse
import re
import subprocess
import sys
import shutil
import threading
import time
from collections import deque
from datetime import datetime

VERSION = "2.0.0"

# ── ANSI ─────────────────────────────────────────────────────────────────────
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"
CLEAR  = "\033[2J\033[H"

_ANSI_RE = re.compile(r"\033\[[^m]*m")


def _strip(s):
    return _ANSI_RE.sub("", s)


# ── Ping ─────────────────────────────────────────────────────────────────────
def ping(host, timeout_s):
    """Returns (success: bool, latency_ms: float|None)."""
    w = ["-W", str(timeout_s * 1000)] if sys.platform == "darwin" else ["-W", str(timeout_s)]
    result = subprocess.run(
        ["ping", "-c", "1"] + w + [host],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if result.returncode != 0:
        return False, None
    m = re.search(r"time[=<]\s*([\d.,]+)", result.stdout)
    if m:
        return True, float(m.group(1).replace(",", "."))
    # Fallback: round-trip stats line "= min/avg/max" (macOS edge case)
    m = re.search(r"=\s*([\d.]+)/([\d.]+)/", result.stdout)
    if m:
        return True, float(m.group(1))
    return True, None


# ── Graph ─────────────────────────────────────────────────────────────────────
def render_graph(history, width, height):
    data = list(history)[-width:]
    data = [None] * (width - len(data)) + data
    valid = [v for v in data if v is not None]
    if not valid:
        return [" " * width] * height, {}
    lo, hi = min(valid), max(valid)
    if hi == lo:
        hi = lo + 1

    def to_row(v):
        return height - 1 - int(round((v - lo) / (hi - lo) * (height - 1)))

    col_rows = [to_row(v) if v is not None else None for v in data]
    grid = [[" "] * width for _ in range(height)]
    for i, row in enumerate(col_rows):
        if row is None:
            grid[height // 2][i] = "!"
            continue
        grid[row][i] = "*"
        if i > 0 and col_rows[i - 1] is not None:
            prev = col_rows[i - 1]
            for r in range(min(prev, row) + 1, max(prev, row)):
                grid[r][i] = "|"
    rows = ["".join(r) for r in grid]
    y_labels = {
        0:            f"{hi:.0f}ms",
        height // 2:  f"{(hi + lo) / 2:.0f}ms",
        height - 1:   f"{lo:.0f}ms",
    }
    return rows, y_labels


# ── Draw ─────────────────────────────────────────────────────────────────────
def draw(states, hosts, cfg):
    cols = shutil.get_terminal_size((80, 24)).columns
    sep_w = min(cols - 1, 72)
    sep = "\u2500" * sep_w
    graph_w = max(10, sep_w - 8)   # 8 = y-label prefix width
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nc = cfg.no_color

    def cc(*codes):
        return "" if nc else "".join(codes)

    lines = [
        cc(BOLD) + sep + cc(RESET),
        cc(BOLD) + "  PING MONITOR" + cc(RESET) +
            f"    {cc(DIM)}v{VERSION}  {now}{cc(RESET)}",
        sep,
    ]

    for idx, host in enumerate(hosts):
        st = states[host]
        lat_str = f"{st['latency']:.1f}ms" if st["latency"] is not None else "\u2014"
        down_str = (
            f"  (down {time.time() - st['outage_start']:.0f}s)"
            if st["outage_start"] else ""
        )
        next_str = f"in {st['next_in']}s" if st["next_in"] > 0 else "pinging\u2026"

        lines.append(f"  {cc(BOLD)}{host}{cc(RESET)}")
        lines.append(
            f"  Status   : {cc(st['color'], BOLD)}{st['label']:<12}{cc(RESET)}"
            f"{st['detail']}{down_str}"
            f"   {cc(DIM)}lat {lat_str}   next {next_str}{cc(RESET)}"
        )
        lines.append(sep)

        graph_rows, y_labels = render_graph(st["graph"], graph_w, cfg.graph_height)
        for r, row_str in enumerate(graph_rows):
            label = y_labels.get(r, "")
            prefix = f"{label:>6} \u2524" if label else "       \u2502"
            if nc:
                lines.append(f"{prefix}{row_str}")
            else:
                colored = row_str.replace("!", f"{RED}!{RESET}{GREEN}")
                lines.append(f"{DIM}{prefix}{RESET}{GREEN}{colored}{RESET}")

        x_axis = " " * 7 + "\u2514" + "\u2500" * max(0, graph_w - 5) + " time \u2192"
        lines.append(cc(DIM) + x_axis + cc(RESET))
        lines.append(sep)
        lines.append(f"  {cc(DIM)}Recent events:{cc(RESET)}")
        for entry in st["log"][-cfg.max_log:]:
            lines.append(f"  {entry if not nc else _strip(entry)}")

        if idx < len(hosts) - 1:
            lines.append("")   # spacer between hosts

    sys.stdout.write(CLEAR + "\n".join(lines) + "\n")
    sys.stdout.flush()


# ── Logging / alerting ────────────────────────────────────────────────────────
def _ts():
    return datetime.now().strftime("%H:%M:%S")


def add_log(st, color, label, detail="", cfg=None, host=None):
    nc = cfg.no_color if cfg else False
    entry = (
        f"{'   ' if nc else DIM}{_ts()}{'   ' if nc else RESET}"
        f"  {'   ' if nc else color}{label:<14}{'   ' if nc else RESET}{detail}"
    )
    st["log"].append(entry)
    if cfg and cfg.log:
        host_tag = f"[{host}] " if host else ""
        line = f"{datetime.now().isoformat(timespec='seconds')}  {host_tag}{label:<14}{_strip(detail)}\n"
        try:
            with open(cfg.log, "a") as f:
                f.write(line)
        except OSError:
            pass


def _send_alert(title, body):
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e", f'display notification "{body}" with title "{title}"'],
                timeout=3, capture_output=True,
            )
        else:
            subprocess.run(["notify-send", title, body], timeout=3, capture_output=True)
    except Exception:
        pass


def fire_alert(title, body):
    threading.Thread(target=_send_alert, args=(title, body), daemon=True).start()


# ── State helpers ─────────────────────────────────────────────────────────────
def _handle_success(host, st, latency, cfg):
    st["graph"].append(latency)
    if latency is not None:
        st["samples"].append(latency)
    st["latency"] = latency

    if st["outage_start"] is not None:
        duration = time.time() - st["outage_start"]
        st["outage_start"] = None
        st["color"] = GREEN
        st["label"] = "RECOVERED"
        st["detail"] = f"  (outage lasted {duration:.0f}s)"
        lat_note = f"  lat={latency:.1f}ms" if latency is not None else ""
        add_log(st, GREEN, "RECOVERED", f"  outage {duration:.0f}s{lat_note}", cfg=cfg, host=host)
        if cfg.alert:
            fire_alert("Ping Monitor", f"{host} recovered after {duration:.0f}s")
        return

    # Check latency threshold
    samples = st["samples"]
    avg = sum(samples) / len(samples) if samples else latency
    high = bool(cfg.warn_ms and avg is not None and avg > cfg.warn_ms)
    was_high = st.get("high_lat", False)
    st["high_lat"] = high

    if high:
        st["color"] = YELLOW
        st["label"] = "HIGH LAT"
        st["detail"] = f"  avg {avg:.0f}ms > {cfg.warn_ms:.0f}ms"
        if not was_high:
            add_log(st, YELLOW, "HIGH LAT",
                    f"  avg {avg:.0f}ms exceeds {cfg.warn_ms:.0f}ms threshold",
                    cfg=cfg, host=host)
    else:
        st["color"] = GREEN
        st["label"] = "OK"
        st["detail"] = ""
        if was_high:
            lat_s = f"  lat back to normal ({latency:.1f}ms)" if latency else ""
            add_log(st, GREEN, "OK", lat_s, cfg=cfg, host=host)
        else:
            add_log(st, GREEN, "OK",
                    f"  {latency:.1f}ms" if latency is not None else "",
                    cfg=cfg, host=host)


def _handle_outage(host, st, cfg):
    st["graph"].append(None)
    if st["outage_start"] is None:
        st["outage_start"] = time.time()
        add_log(st, RED, "OUTAGE", "  entering recovery mode", cfg=cfg, host=host)
        if cfg.alert:
            fire_alert("Ping Monitor", f"{host} is unreachable")
    st["color"] = RED
    st["label"] = "OUTAGE"
    st["detail"] = ""


# ── Monitor thread ────────────────────────────────────────────────────────────
def monitor_host(host, st, lock, shutdown, cfg):
    while not shutdown.is_set():
        with lock:
            st["next_in"] = 0

        # Ping outside lock so the render thread isn't blocked
        success, latency = ping(host, cfg.timeout)

        if success:
            with lock:
                _handle_success(host, st, latency, cfg)
            interval = cfg.interval
        else:
            with lock:
                already_in_outage = st["outage_start"] is not None

            if already_in_outage:
                # Stay in OUTAGE silently — no retry loop, no FAIL/RETRY log entries
                with lock:
                    _handle_outage(host, st, cfg)
                interval = cfg.retry_interval
            else:
                # Retry loop — each ping is outside the lock
                retry_success, retry_lat = False, None
                for attempt in range(1, cfg.retries + 1):
                    if shutdown.is_set():
                        return
                    with lock:
                        st["color"] = YELLOW
                        st["label"] = "RETRYING"
                        st["detail"] = f"  ({attempt}/{cfg.retries})"
                        add_log(st, YELLOW, "FAIL", f"  retry {attempt}/{cfg.retries}",
                                cfg=cfg, host=host)
                    success, latency = ping(host, cfg.timeout)
                    if success:
                        retry_success, retry_lat = True, latency
                        break

                with lock:
                    if retry_success:
                        _handle_success(host, st, retry_lat, cfg)
                        interval = cfg.interval
                    else:
                        _handle_outage(host, st, cfg)
                        interval = cfg.retry_interval

        # Countdown — hold lock only briefly per tick
        for remaining in range(interval, 0, -1):
            if shutdown.is_set():
                return
            with lock:
                st["next_in"] = remaining
            time.sleep(1)


# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(
        prog="ping_monitor.py",
        description="Terminal-based network connectivity monitor.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  ping_monitor.py                         monitor 8.8.8.8 with defaults
  ping_monitor.py 1.1.1.1 -i 5           monitor Cloudflare DNS every 5s
  ping_monitor.py 8.8.8.8 192.168.1.1    monitor two hosts simultaneously
  ping_monitor.py 8.8.8.8 --warn-ms 50   amber alert when avg latency > 50ms
  ping_monitor.py 8.8.8.8 -l events.log  append events to a log file
  ping_monitor.py 8.8.8.8 --alert        desktop notification on outage/recovery
""",
    )
    p.add_argument("hosts", nargs="*", default=["8.8.8.8"], metavar="HOST",
                   help="Host(s) to ping (default: 8.8.8.8). Multiple hosts run simultaneously.")
    p.add_argument("-i", "--interval", type=int, default=15, metavar="SECS",
                   help="Seconds between pings when healthy (default: 15)")
    p.add_argument("-R", "--retry-interval", type=int, default=2, metavar="SECS",
                   help="Seconds between pings during outage (default: 2)")
    p.add_argument("-r", "--retries", type=int, default=2, metavar="N",
                   help="Immediate retries before declaring outage (default: 2)")
    p.add_argument("-t", "--timeout", type=int, default=3, metavar="SECS",
                   help="Ping wait timeout in seconds (default: 3)")
    p.add_argument("-l", "--log", metavar="FILE",
                   help="Append state-change events to FILE")
    p.add_argument("--warn-ms", type=float, metavar="MS",
                   help="Warn (HIGH LAT) when rolling avg latency exceeds MS milliseconds")
    p.add_argument("--alert", action="store_true",
                   help="Send desktop notification on outage and recovery")
    p.add_argument("--no-color", action="store_true",
                   help="Disable ANSI color output")
    p.add_argument("--graph-height", type=int, default=8, metavar="ROWS",
                   help="Graph height in rows (default: 8)")
    p.add_argument("--max-log", type=int, default=8, metavar="N",
                   help="Recent events shown per host (default: 8)")
    p.add_argument("--graph-max", type=int, default=300, metavar="N",
                   help="Rolling graph sample window (default: 300)")
    return p.parse_args()


def make_state(graph_max):
    return {
        "color":        DIM,
        "label":        "STARTING",
        "detail":       "",
        "latency":      None,
        "high_lat":     False,
        "samples":      [],
        "graph":        deque(maxlen=graph_max),
        "outage_start": None,
        "next_in":      0,
        "log":          [],
    }


def main():
    cfg = parse_args()
    hosts = cfg.hosts
    lock = threading.Lock()
    shutdown = threading.Event()
    states = {h: make_state(cfg.graph_max) for h in hosts}

    for host in hosts:
        threading.Thread(
            target=monitor_host,
            args=(host, states[host], lock, shutdown, cfg),
            daemon=True,
        ).start()

    try:
        while True:
            with lock:
                draw(states, hosts, cfg)
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown.set()
        parts = []
        for host in hosts:
            s = states[host]["samples"]
            avg = f"{sum(s) / len(s):.1f}ms" if s else "n/a"
            parts.append(f"  {host}: samples={len(s)}  avg={avg}")
        sys.stdout.write("\n  Monitor stopped.\n" + "\n".join(parts) + "\n\n")
        sys.stdout.flush()
        sys.exit(0)


if __name__ == "__main__":
    main()
