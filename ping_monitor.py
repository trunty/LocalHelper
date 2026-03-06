#!/usr/bin/env python3
import re
import subprocess
import time
import sys
import shutil
from collections import deque
from datetime import datetime

VERSION = "1.4.1"

TARGET = "8.8.8.8"
NORMAL_INTERVAL = 15   # seconds between pings when healthy
RETRY_INTERVAL = 2     # seconds between pings when recovering
MAX_RETRIES = 2        # immediate retries before entering recovery mode
MAX_LOG = 8            # recent events shown on screen
GRAPH_HEIGHT = 8       # rows tall for the latency graph
GRAPH_MAX = 300        # rolling sample window

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
    # macOS ping -W takes milliseconds; Linux takes seconds
    wait_arg = ["-W", "3000"] if sys.platform == "darwin" else ["-W", "3"]
    result = subprocess.run(
        ["ping", "-c", "1"] + wait_arg + [host],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        return False, None
    # Primary: per-packet "time=X.X ms" line
    match = re.search(r"time[=<]\s*([\d.,]+)", result.stdout)
    if match:
        return True, float(match.group(1).replace(",", "."))
    # Fallback: round-trip stats "= min/avg/max/stddev" line (macOS)
    match = re.search(r"=\s*([\d.]+)/([\d.]+)/", result.stdout)
    if match:
        return True, float(match.group(1))  # use min
    return True, None


def render_graph(history, width, height):
    """
    Renders a scrolling line graph from a deque of (float|None) latency values.
    Returns (row_strings, y_label_map) where row_strings are plain ASCII and
    y_label_map is {row_index: label_str}.
    """
    data = list(history)[-width:]
    data = [None] * (width - len(data)) + data   # left-pad with None

    valid = [v for v in data if v is not None]
    if not valid:
        return [" " * width] * height, {}

    lo, hi = min(valid), max(valid)
    if hi == lo:
        hi = lo + 1

    def to_row(v):
        # row 0 = top (high latency), row height-1 = bottom (low latency)
        normalized = (v - lo) / (hi - lo)
        return height - 1 - int(round(normalized * (height - 1)))

    col_rows = [to_row(v) if v is not None else None for v in data]

    grid = [[" "] * width for _ in range(height)]

    for i, row in enumerate(col_rows):
        if row is None:
            grid[height // 2][i] = "!"   # outage marker
            continue

        grid[row][i] = "*"               # data point

        # Vertical connector to previous point
        if i > 0 and col_rows[i - 1] is not None:
            prev = col_rows[i - 1]
            if prev != row:
                for r in range(min(prev, row) + 1, max(prev, row)):
                    grid[r][i] = "|"

    rows = ["".join(row) for row in grid]
    y_labels = {
        0:            f"{hi:.0f}ms",
        height // 2:  f"{(hi + lo) / 2:.0f}ms",
        height - 1:   f"{lo:.0f}ms",
    }
    return rows, y_labels


def draw(state):
    cols = shutil.get_terminal_size((80, 24)).columns
    sep_w = min(cols - 1, 72)
    sep = "\u2500" * sep_w

    # Y-axis prefix is 8 chars: "  99ms \u2524" or "       \u2502"
    y_label_w = 8
    graph_w = max(10, sep_w - y_label_w)

    lat_str = f"{state['latency']:.1f}ms" if state["latency"] is not None else "\u2014"
    down_str = (
        f"  (down {time.time() - state['outage_start']:.0f}s)"
        if state["outage_start"] else ""
    )
    next_str = f"in {state['next_in']}s" if state["next_in"] > 0 else "pinging\u2026"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    graph_rows, y_labels = render_graph(state["graph"], graph_w, GRAPH_HEIGHT)

    lines = [
        f"{BOLD}{sep}{RESET}",
        f"{BOLD}  PING MONITOR  \u2192  {TARGET}{RESET}    {DIM}v{VERSION}  {now}{RESET}",
        f"{sep}",
        (
            f"  Status   : {state['color']}{BOLD}{state['label']:<12}{RESET}"
            f"{state['detail']}{down_str}"
            f"   {DIM}lat {lat_str}   next {next_str}{RESET}"
        ),
        f"{sep}",
    ]

    for r, row_str in enumerate(graph_rows):
        label = y_labels.get(r, "")
        prefix = f"{label:>6} \u2524" if label else "       \u2502"
        # Highlight outage markers red, rest of row green
        colored = row_str.replace("!", f"{RED}!{RESET}{GREEN}")
        lines.append(f"{DIM}{prefix}{RESET}{GREEN}{colored}{RESET}")

    # X-axis bottom: 7 spaces align the corner under the \u2502 above
    x_axis = " " * 7 + "\u2514" + "\u2500" * max(0, graph_w - 5) + " time \u2192"
    lines.append(f"{DIM}{x_axis}{RESET}")

    lines.append(f"{sep}")
    lines.append(f"  {DIM}Recent events:{RESET}")
    for entry in state["log"][-MAX_LOG:]:
        lines.append(f"  {entry}")

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
        "graph": deque(maxlen=GRAPH_MAX),
        "outage_start": None,
        "next_in": 0,
        "log": [],
    }

    try:
        while True:
            draw(state)
            success, latency = ping(TARGET)

            if success:
                state["graph"].append(latency)
                if latency is not None:
                    state["samples"].append(latency)
                state["latency"] = latency
                if state["outage_start"] is not None:
                    duration = time.time() - state["outage_start"]
                    state["outage_start"] = None
                    state["color"] = GREEN
                    state["label"] = "RECOVERED"
                    state["detail"] = f"  (outage lasted {duration:.0f}s)"
                    add_log(state["log"], GREEN, "RECOVERED",
                            f"  outage {duration:.0f}s  lat={latency:.1f}ms"
                            if latency is not None else f"  outage {duration:.0f}s")
                else:
                    state["color"] = GREEN
                    state["label"] = "OK"
                    state["detail"] = ""
                    add_log(state["log"], GREEN, "OK",
                            f"  {latency:.1f}ms" if latency is not None else "")
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
                    state["graph"].append(latency)
                    if latency is not None:
                        state["samples"].append(latency)
                    state["latency"] = latency
                    if state["outage_start"] is not None:
                        duration = time.time() - state["outage_start"]
                        state["outage_start"] = None
                        state["color"] = GREEN
                        state["label"] = "RECOVERED"
                        state["detail"] = f"  (outage lasted {duration:.0f}s)"
                        add_log(state["log"], GREEN, "RECOVERED",
                                f"  outage {duration:.0f}s  lat={latency:.1f}ms"
                                if latency is not None else f"  outage {duration:.0f}s")
                    else:
                        state["color"] = GREEN
                        state["label"] = "OK"
                        state["detail"] = "  (recovered on retry)"
                        add_log(state["log"], GREEN, "OK (retry)",
                                f"  {latency:.1f}ms" if latency is not None else "")
                    countdown(NORMAL_INTERVAL, state)
                else:
                    state["graph"].append(None)   # record outage point
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
        sys.stdout.write(
            f"\n  Monitor stopped.  samples={len(samples)}  overall avg={avg_str}\n\n"
        )
        sys.stdout.flush()
        sys.exit(0)


if __name__ == "__main__":
    main()
