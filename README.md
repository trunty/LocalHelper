# ping_monitor.py

A terminal-based network connectivity monitor with a persistent, non-scrolling dashboard and ANSI color output. Designed to run continuously in a terminal window and give you an at-a-glance view of your internet connection health.

---

## Repository Layout

| Path | Description |
|---|---|
| `ping_monitor.py` | **Stable release** — current production version (v2.0.0) |
| [`beta/`](beta/) | **Early access** — next version in active development; all code changes go here first |
| [`archive/`](archive/) | **Previous stable releases** — when a new version is promoted to production, the outgoing version is added here as `ping_monitor_vX.Y.Z.py`; files are never removed or replaced |

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Dashboard Layout](#dashboard-layout)
- [Status States](#status-states)
- [Color Coding](#color-coding)
- [How It Works](#how-it-works)
  - [Normal Operation](#normal-operation)
  - [Failure Detection](#failure-detection)
  - [Outage Mode](#outage-mode)
  - [Recovery](#recovery)
- [Latency Tracking](#latency-tracking)
- [Graceful Shutdown](#graceful-shutdown)
- [Known Limitations](#known-limitations)
- [Potential Expansions](#potential-expansions)

---

## Overview

`ping_monitor.py` continuously pings one or more hosts and displays results in a fixed, persistent terminal dashboard that redraws in place rather than scrolling. It distinguishes between transient blips (handled with fast retries) and sustained outages (tracked with elapsed time), and uses color to communicate connection health at a glance. All settings are configurable via CLI flags — no script editing required.

---

## Features

- **Persistent dashboard** — the display redraws in place using ANSI escape codes; no scrolling
- **Multi-host monitoring** — pass multiple hosts as positional arguments; each gets its own status row and graph, running in parallel threads
- **CLI configuration** — all settings via `argparse` flags; no script editing required
- **Live countdown** — shows seconds until next ping, updating every second
- **Color-coded status** — green for healthy, amber for retrying/high-latency, red for outage
- **Fast retry logic** — immediately retries on first failure before declaring an outage
- **Outage tracking** — records when the outage started and displays elapsed down time; retries silently at `--retry-interval` without spamming the log
- **Recovery detection** — reports total outage duration when connectivity is restored
- **Latency statistics** — tracks latest and rolling average round-trip time across the session
- **Latency threshold warning** — `--warn-ms` triggers an amber `HIGH LAT` status when rolling average exceeds the threshold, even without packet loss
- **Scrolling latency graph** — live ASCII line graph showing up to 300 samples with labeled Y-axis
- **Scrolling event log** — shows the last 8 state-change events per host with timestamps
- **Log file output** — `--log FILE` appends events to a plain-text file with ISO timestamps
- **Desktop alerts** — `--alert` sends native notifications on outage and recovery (macOS: `osascript`; Linux: `notify-send`)
- **Graceful shutdown** — Ctrl+C prints a session summary before exiting
- **No dependencies** — uses only Python standard library modules

---

## Requirements

- Python 3.6 or later
- A Unix-like operating system (Linux, macOS)
- The system `ping` command available in `$PATH`
- A terminal that supports ANSI escape codes (virtually all modern terminals do)

---

## Installation

No installation is required. Clone the repo or download the script directly:

```bash
# Clone the repo
git clone https://github.com/trunty/LocalHelper.git
cd LocalHelper

# Or download the script directly
curl -o ping_monitor.py \
  https://raw.githubusercontent.com/trunty/LocalHelper/claude/session_01SGvFjLFQQ3hRqmCR9AtYLd/ping_monitor.py
```

Make it executable (optional):

```bash
chmod +x ping_monitor.py
```

---

## Usage

```bash
python3 ping_monitor.py [HOST ...] [OPTIONS]
```

With no arguments, monitors `8.8.8.8` using sensible defaults. To stop, press `Ctrl+C` — a session summary is printed before exit.

---

## Configuration

All settings are passed as CLI flags:

| Flag | Default | Description |
|---|---|---|
| `HOST` (positional, repeatable) | `8.8.8.8` | Host(s) to ping. Pass multiple for simultaneous monitoring. |
| `-i / --interval SECS` | `15` | Seconds between pings when healthy. |
| `-R / --retry-interval SECS` | `2` | Seconds between pings during an outage. |
| `-r / --retries N` | `2` | Immediate retries before declaring an outage. |
| `-t / --timeout SECS` | `3` | Ping wait timeout per attempt. |
| `-l / --log FILE` | _(none)_ | Append state-change events to a file. |
| `--warn-ms MS` | _(none)_ | Amber `HIGH LAT` warning when rolling avg latency exceeds MS. |
| `--alert` | off | Desktop notification on outage and recovery. |
| `--no-color` | off | Disable ANSI color output. |
| `--graph-height ROWS` | `8` | Height of the latency graph. |
| `--max-log N` | `8` | Recent events shown per host. |
| `--graph-max N` | `300` | Rolling graph sample window (number of data points). |

**Examples:**

```bash
# Defaults
python3 ping_monitor.py

# Monitor two hosts simultaneously
python3 ping_monitor.py 8.8.8.8 1.1.1.1

# Aggressive polling with latency warning and log file
python3 ping_monitor.py 8.8.8.8 -i 5 -R 1 --warn-ms 50 -l ~/ping.log --alert
```

---

## Dashboard Layout

```
────────────────────────────────────────────────────────────────────────
  PING MONITOR  →  8.8.8.8    v2.0.0  2026-03-06 14:22:10
────────────────────────────────────────────────────────────────────────
  Status   : OK              lat 14.2ms   next in 11s
────────────────────────────────────────────────────────────────────────
  28ms ╪                              *
       │                           *  |
  21ms ╪            *   *       *  |
       │          * | * | *   * |
       │        * | | | | | * | |
  14ms ╪  * * * | | | | | | | | |
       │  | | |
       │
       └─────────────────────────────────────────────────── time →
────────────────────────────────────────────────────────────────────────
  Recent events:
  14:22:10  OK              14.2ms
  14:21:55  OK              13.9ms
  ...
```

**During an outage:**

```
────────────────────────────────────────────────────────────────────────
  PING MONITOR  →  8.8.8.8    v2.0.0  2026-03-06 14:25:03
────────────────────────────────────────────────────────────────────────
  Status   : OUTAGE         (down 47s)   lat —   next in 1s
────────────────────────────────────────────────────────────────────────
  ...graph with ! markers where outage samples appear...
────────────────────────────────────────────────────────────────────────
  Recent events:
  14:24:16  OUTAGE          entering recovery mode
  14:24:14  FAIL            retry 2/2
  14:24:12  FAIL            retry 1/2
  14:24:10  OK              14.0ms
  ...
```

The graph Y-axis is auto-scaled to the min/max latency seen in the current window. Outage samples (failed pings) appear as `!` markers at the vertical midpoint.

---

## Status States

| Label | Meaning |
|---|---|
| `STARTING` | Script has just launched, first ping not yet complete. |
| `OK` | Most recent ping succeeded within the normal timeout. |
| `OK (retry)` | Ping initially failed but succeeded on a retry attempt. |
| `HIGH LAT` | Pings succeeding but rolling avg latency exceeds `--warn-ms`. Clears automatically. |
| `RETRYING` | First ping failed; currently performing immediate retry attempts. |
| `OUTAGE` | All retries exhausted; connection is considered down. Polling silently at `--retry-interval`. |
| `RECOVERED` | Connection restored after a sustained outage; shows total outage duration. |

---

## Color Coding

| Color | Meaning |
|---|---|
| Green | Connection is healthy (`OK`, `RECOVERED`) |
| Amber / Yellow | Transient failure being retried (`RETRYING`, `FAIL`) or latency threshold exceeded (`HIGH LAT`) |
| Red | Sustained outage (`OUTAGE`) |
| Dim / Grey | Script is starting up or informational text |

Colors are rendered using standard ANSI escape codes and will display correctly in any modern terminal emulator (iTerm2, Terminal.app, GNOME Terminal, Windows Terminal, etc.).

---

## How It Works

### Normal Operation

Each host runs in its own background thread. The main thread redraws the full dashboard every second. On each monitor cycle, a host thread:

1. Calls `ping -c 1 -W <timeout> <HOST>` via subprocess
2. Parses the round-trip time from stdout using a regex
3. Updates shared state (protected by a per-host lock) and appends to the rolling graph
4. Counts down `--interval` in 1-second ticks before the next ping

### Failure Detection

When a ping fails (non-zero exit code from `ping`), the script does not immediately declare an outage. Instead it performs up to `MAX_RETRIES` back-to-back retries with no delay between them. This handles transient packet loss without triggering false outage alerts.

- If any retry succeeds → status returns to `OK (retry)` and normal interval resumes
- If all retries fail → an outage is declared

### Outage Mode

Once an outage is declared:

- `outage_start` timestamp is recorded
- Status changes to `OUTAGE` (red)
- The dashboard shows elapsed down time, updated every second
- Polling continues at the faster `--retry-interval` cadence
- Subsequent failed pings stay silently in `OUTAGE` — no `RETRYING` display or `FAIL` log entries until connectivity is restored

### Recovery

When a ping succeeds after a recorded outage:

- Total outage duration is calculated from `outage_start`
- Status changes to `RECOVERED` (green) with the duration displayed
- Normal polling interval resumes
- `outage_start` is cleared

---

## Latency Tracking

Latency is parsed from `ping` output using a two-stage strategy:

1. **Per-packet line** — regex `time[=<]\s*([\d.,]+)` matches formats like `time=14.2 ms` and `time<1ms`
2. **Round-trip stats fallback** — regex `=\s*([\d.]+)/([\d.]+)/` parses the `min/avg/max/stddev` summary line; the minimum value is used

The fallback handles a macOS edge case: `ping -W` takes milliseconds on macOS vs. seconds on Linux, so the script uses `-W 3000` on macOS and `-W 3` on Linux. The per-packet line is expected in both cases; the stats-line fallback is a belt-and-suspenders safety net.

If latency cannot be parsed despite a successful ping, it is recorded as `None`:

- `None` latencies are not added to the samples list
- The average is computed only over valid numeric samples
- The display shows `—` for the current latency
- Graph samples with no latency are plotted as `!` outage markers

---

## Graceful Shutdown

Pressing `Ctrl+C` triggers a `KeyboardInterrupt` which is caught cleanly. Before exiting, the script prints:

```
  Monitor stopped.  samples=87  overall avg=13.9ms
```

This gives you a quick summary of session quality. The terminal is left in a usable state (the dashboard is not erased — it remains visible as the last output).

---

## Known Limitations

- **Stats reset on restart** — there is no persistence between runs.
- **ANSI terminals only** — the persistent display will not work correctly if output is redirected to a file or piped. Use `--no-color` and pipe through `col -b` to strip escape codes if needed.
- **`--alert` on Linux** requires `notify-send` (`libnotify-bin`). If absent the flag is silently ignored.
- **Tall dashboards** — with many hosts and a short terminal the display may overflow. Reduce `--graph-height` and `--max-log` to compensate.

---

## Potential Expansions

- **Webhook alerts** — POST to a Slack, Discord, or custom webhook on state changes
- **Config file support** — read settings from a YAML or INI file
- **Stats persistence** — append session summaries to a JSON or CSV file for trend analysis
