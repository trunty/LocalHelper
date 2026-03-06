# ping_monitor.py

A terminal-based network connectivity monitor with a persistent, non-scrolling dashboard and ANSI color output. Designed to run continuously in a terminal window and give you an at-a-glance view of your internet connection health.

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

`ping_monitor.py` continuously pings a target host (default: `8.8.8.8`, Google's public DNS) and displays the result in a fixed, persistent terminal dashboard that redraws in place rather than scrolling. It distinguishes between transient blips (handled with fast retries) and sustained outages (tracked with elapsed time), and uses color to communicate connection health at a glance.

---

## Features

- **Persistent dashboard** — the display redraws in place using ANSI escape codes; no scrolling
- **Live countdown** — shows seconds until next ping, updating every second
- **Color-coded status** — green for healthy, amber for retrying, red for outage
- **Fast retry logic** — immediately retries on first failure before declaring an outage
- **Outage tracking** — records when the outage started and displays elapsed down time
- **Recovery detection** — reports total outage duration when connectivity is restored
- **Latency statistics** — tracks latest and average round-trip time across the session
- **Scrolling event log** — shows the last 10 status events with timestamps
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
python3 ping_monitor.py
```

Or if made executable:

```bash
./ping_monitor.py
```

To stop the monitor, press `Ctrl+C`. A summary of the session will be printed before the script exits.

---

## Configuration

All configuration is done via constants at the top of the script. There is no CLI argument parsing — edit the values directly:

| Constant | Default | Description |
|---|---|---|
| `TARGET` | `"8.8.8.8"` | Host to ping. Can be an IP address or hostname. |
| `NORMAL_INTERVAL` | `15` | Seconds between pings when the connection is healthy. |
| `RETRY_INTERVAL` | `2` | Seconds between pings when in outage/recovery mode. |
| `MAX_RETRIES` | `2` | Number of immediate retries before declaring an outage. |
| `MAX_LOG` | `10` | Number of recent events shown in the event log panel. |

**Example — monitor a custom host with aggressive polling:**

```python
TARGET = "192.168.1.1"   # your router
NORMAL_INTERVAL = 5
RETRY_INTERVAL = 1
MAX_RETRIES = 3
```

---

## Dashboard Layout

```
──────────────────────────────────────────────────────────
  PING MONITOR  →  8.8.8.8    2026-03-06 14:22:10
──────────────────────────────────────────────────────────
  Status   : OK
  Latency  : 14.2ms   avg 13.8ms over 42 samples
  Next ping: in 11s
──────────────────────────────────────────────────────────
  Recent events:
  14:22:10  OK              14.2ms
  14:21:55  OK              13.9ms
  14:21:40  OK              14.1ms
  14:21:25  OK              13.6ms
  ...
```

**During an outage:**

```
──────────────────────────────────────────────────────────
  PING MONITOR  →  8.8.8.8    2026-03-06 14:25:03
──────────────────────────────────────────────────────────
  Status   : OUTAGE      (down 47s)
  Latency  : —   avg 13.8ms over 42 samples
  Next ping: in 1s
──────────────────────────────────────────────────────────
  Recent events:
  14:24:16  OUTAGE          entering recovery mode
  14:24:14  FAIL            retry 2/2
  14:24:12  FAIL            retry 1/2
  14:24:10  OK              14.0ms
  ...
```

---

## Status States

| Label | Meaning |
|---|---|
| `STARTING` | Script has just launched, first ping not yet complete. |
| `OK` | Most recent ping succeeded within the normal timeout. |
| `OK (retry)` | Ping initially failed but succeeded on a retry attempt. |
| `RETRYING` | First ping failed; currently performing immediate retry attempts. |
| `OUTAGE` | All retries exhausted; connection is considered down. Now polling at `RETRY_INTERVAL`. |
| `RECOVERED` | Connection restored after a sustained outage; shows total outage duration. |

---

## Color Coding

| Color | Meaning |
|---|---|
| Green | Connection is healthy (`OK`, `RECOVERED`) |
| Amber / Yellow | Transient failure being retried (`RETRYING`, `FAIL`) |
| Red | Sustained outage (`OUTAGE`) |
| Dim / Grey | Script is starting up or informational text |

Colors are rendered using standard ANSI escape codes and will display correctly in any modern terminal emulator (iTerm2, Terminal.app, GNOME Terminal, Windows Terminal, etc.).

---

## How It Works

### Normal Operation

On each cycle, the script:

1. Renders the current state to the terminal (clearing and redrawing from the top)
2. Calls `ping -c 1 -W 3 <TARGET>` via subprocess
3. Parses the round-trip time from stdout using a regex
4. Updates state and logs the result
5. Counts down the `NORMAL_INTERVAL` in 1-second ticks, redrawing each second

### Failure Detection

When a ping fails (non-zero exit code from `ping`), the script does not immediately declare an outage. Instead it performs up to `MAX_RETRIES` back-to-back retries with no delay between them. This handles transient packet loss without triggering false outage alerts.

- If any retry succeeds → status returns to `OK (retry)` and normal interval resumes
- If all retries fail → an outage is declared

### Outage Mode

Once an outage is declared:

- `outage_start` timestamp is recorded
- Status changes to `OUTAGE` (red)
- The dashboard shows elapsed down time, updated every second
- Polling continues at the faster `RETRY_INTERVAL` cadence
- Each poll still goes through the full retry sequence on failure

### Recovery

When a ping succeeds after a recorded outage:

- Total outage duration is calculated from `outage_start`
- Status changes to `RECOVERED` (green) with the duration displayed
- Normal polling interval resumes
- `outage_start` is cleared

---

## Latency Tracking

Latency is parsed from the `ping` output using the regex:

```
time[=<]([\d.]+)\s*ms
```

This handles both `time=14.2ms` and `time=14.2 ms` formats, as well as the `time<1ms` format seen on some systems.

**Important:** On some platforms (notably macOS), the `ping` command may return exit code 0 (success) but produce output that does not match this pattern — for example when the response time is extremely low or the output format differs slightly. In this case `latency` will be `None`. The script handles this gracefully:

- `None` latencies are not added to the samples list
- The average is computed only over valid numeric samples
- The display shows `—` for the current latency

---

## Graceful Shutdown

Pressing `Ctrl+C` triggers a `KeyboardInterrupt` which is caught cleanly. Before exiting, the script prints:

```
  Monitor stopped.  samples=87  overall avg=13.9ms
```

This gives you a quick summary of session quality. The terminal is left in a usable state (the dashboard is not erased — it remains visible as the last output).

---

## Known Limitations

- **Single target only** — the script monitors one host. Running multiple instances in separate terminal windows/panes is the simplest workaround.
- **No log file** — all output is to stdout only; nothing is persisted to disk.
- **No alerting** — there is no notification system (email, webhook, desktop alert, etc.).
- **No latency threshold warnings** — high latency without packet loss is not flagged.
- **Stats reset on restart** — there is no persistence between runs.
- **ANSI terminals only** — the persistent display will not work correctly if output is redirected to a file or piped.

---

## Potential Expansions

The script is intentionally simple and structured around a single `state` dict, making it straightforward to extend:

- **Multiple targets** — run one monitoring loop per host and display them in rows
- **Log file output** — write events to a file in addition to the screen
- **Latency threshold alerting** — flag when avg latency exceeds a configurable threshold even if pings succeed
- **Desktop/audio notifications** — trigger `osascript` (macOS) or `notify-send` (Linux) on outage/recovery
- **Webhook alerts** — POST to a Slack, Discord, or custom webhook on state changes
- **Historical graphs** — use `curses` or a sparkline library to render latency history inline
- **Config file support** — read settings from a YAML or INI file instead of hardcoded constants
- **Stats persistence** — append session summaries to a JSON or CSV file for trend analysis
