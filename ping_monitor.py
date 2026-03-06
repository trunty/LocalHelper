#!/usr/bin/env python3
import re
import subprocess
import time
import sys
from datetime import datetime

TARGET = "8.8.8.8"
NORMAL_INTERVAL = 15   # seconds between pings when healthy
RETRY_INTERVAL = 2     # seconds between pings when recovering
MAX_RETRIES = 2        # immediate retries before entering recovery mode
MAX_LOG = 10           # recent events shown on screen

GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"
CLEAR  = "\033[2J\033[H"


def timestamp():
    return datetime.now().strftime("%H:%M:%S")


def ping(host):
    """Returns (success, latency_ms). latency_ms is None on failure."""
    result = subprocess.run(
        ["ping", "-c", "1", "-W", "3", host],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return False, None
    match = re.search(r"time[=<]([\d.]+)\s*ms", result.stdout)
    latency = float(match.group(1)) if match else None
    return True, latency


def draw(state):
    samples = state["samples"]
    avg = sum(samples) / len(samples) if samples else None
    avg_str = f"{avg:.1f}ms" if avg is not None else "n/a"
    lat_str = f"{state['latency']:.1f}ms" if state["latency"] is not None else "—"
    down_str = (
        f"  (down {time.time() - state['outage_start']:.0f}s)"
        if state["outage_start"] else ""
    )
    next_str = f"in {state['next_in']}s" if state["next_in"] > 0 else "pinging..."
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"{BOLD}{'─' * 58}{RESET}",
        f"{BOLD}  PING MONITOR  →  {TARGET}{RESET}    {DIM}{now}{RESET}",
        f"{'─' * 58}",
        f"  Status   : {state['color']}{BOLD}{state['label']:<12}{RESET}{state['detail']}{down_str}",
        f"  Latency  : {lat_str}   {DIM}avg {avg_str} over {len(samples)} samples{RESET}",
        f"  Next ping: {DIM}{next_str}{RESET}",
        f"{'─' * 58}",
        f"  {DIM}Recent events:{RESET}",
    ]
    for entry in state["log"][-MAX_LOG:]:
        lines.append(f"  {entry}")
    while len(lines) < MAX_LOG + 9:
        lines.append("")

    sys.stdout.write(CLEAR + "\n".join(lines) + "\n")
    sys.stdout.flush()


def add_log(log, color, label, detail=""):
    log.append(f"{DIM}{timestamp()}{RESET}  {color}{label:<14}{RESET}{detail}")


def countdown(seconds, state):
    for remaining in range(seconds, 0, -1):
        state["next_in"] = remaining
        draw(state)
        time.sleep(1)
    state["next_in"] = 0


def main():
    state = {
        "color": DIM,
        "label": "STARTING",
        "detail": "",
        "latency": None,
        "samples": [],
        "outage_start": None,
        "next_in": 0,
        "log": [],
    }

    try:
        while True:
            draw(state)
            success, latency = ping(TARGET)

            if success:
                state["samples"].append(latency)
                state["latency"] = latency
                if state["outage_start"] is not None:
                    duration = time.time() - state["outage_start"]
                    state["outage_start"] = None
                    state["color"] = GREEN
                    state["label"] = "RECOVERED"
                    state["detail"] = f"  (outage lasted {duration:.0f}s)"
                    add_log(state["log"], GREEN, "RECOVERED", f"  outage {duration:.0f}s  lat={latency:.1f}ms" if latency is not None else f"  outage {duration:.0f}s")
                else:
                    state["color"] = GREEN
                    state["label"] = "OK"
                    state["detail"] = ""
                    add_log(state["log"], GREEN, "OK", f"  {latency:.1f}ms" if latency is not None else "")
                countdown(NORMAL_INTERVAL, state)

            else:
                retry_success = False
                for attempt in range(1, MAX_RETRIES + 1):
                    state["color"] = YELLOW
                    state["label"] = "RETRYING"
                    state["detail"] = f"  ({attempt}/{MAX_RETRIES})"
                    add_log(state["log"], YELLOW, "FAIL", f"  retry {attempt}/{MAX_RETRIES}")
                    draw(state)
                    success, latency = ping(TARGET)
                    if success:
                        retry_success = True
                        break

                if retry_success:
                    state["samples"].append(latency)
                    state["latency"] = latency
                    if state["outage_start"] is not None:
                        duration = time.time() - state["outage_start"]
                        state["outage_start"] = None
                        state["color"] = GREEN
                        state["label"] = "RECOVERED"
                        state["detail"] = f"  (outage lasted {duration:.0f}s)"
                        add_log(state["log"], GREEN, "RECOVERED", f"  outage {duration:.0f}s  lat={latency:.1f}ms" if latency is not None else f"  outage {duration:.0f}s")
                    else:
                        state["color"] = GREEN
                        state["label"] = "OK"
                        state["detail"] = "  (recovered on retry)"
                        add_log(state["log"], GREEN, "OK (retry)", f"  {latency:.1f}ms" if latency is not None else "")
                    countdown(NORMAL_INTERVAL, state)
                else:
                    if state["outage_start"] is None:
                        state["outage_start"] = time.time()
                        add_log(state["log"], RED, "OUTAGE", "  entering recovery mode")
                    state["color"] = RED
                    state["label"] = "OUTAGE"
                    state["detail"] = ""
                    countdown(RETRY_INTERVAL, state)

    except KeyboardInterrupt:
        samples = state["samples"]
        avg = sum(samples) / len(samples) if samples else None
        avg_str = f"{avg:.1f}ms" if avg else "n/a"
        sys.stdout.write(f"\n  Monitor stopped.  samples={len(samples)}  overall avg={avg_str}\n\n")
        sys.stdout.flush()
        sys.exit(0)


if __name__ == "__main__":
    main()
