# ping_monitor.py — Beta (v2.0.0-beta.1)

> **Promoted to production.** This version was promoted to the repo root as v2.0.0. The previous stable release (v1.4.1) has been moved to [`../archive/`](../archive/). Development of the next version will continue here.

---

## What's New in v2.0.0

### CLI flags (argparse)

No more editing the script to change settings. All configuration is now via command-line arguments:

```
python3 ping_monitor.py [HOST ...] [OPTIONS]
```

| Argument | Default | Description |
|---|---|---|
| `HOST` (positional, repeatable) | `8.8.8.8` | Host(s) to ping. Pass multiple for simultaneous monitoring. |
| `-i / --interval SECS` | `15` | Seconds between pings when healthy. |
| `-R / --retry-interval SECS` | `2` | Seconds between pings during an outage. |
| `-r / --retries N` | `2` | Immediate retries before declaring an outage. |
| `-t / --timeout SECS` | `3` | Ping wait timeout per attempt. |
| `-l / --log FILE` | _(none)_ | Append state-change events to a file. |
| `--warn-ms MS` | _(none)_ | Amber `HIGH LAT` warning when rolling avg latency exceeds MS. |
| `--alert` | off | Desktop notification on outage and recovery. |
| `--no-color` | off | Disable ANSI color (useful with `--log` or in plain terminals). |
| `--graph-height ROWS` | `8` | Height of the latency graph. |
| `--max-log N` | `8` | Recent events shown per host. |
| `--graph-max N` | `300` | Rolling graph sample window (number of data points). |

### Multi-host monitoring

Pass multiple hostnames or IPs — each gets its own status row and graph, all running in parallel:

```bash
python3 ping_monitor.py 8.8.8.8 1.1.1.1 192.168.1.1
```

Each host runs in its own background thread. The main thread redraws the entire dashboard every second.

### Log file (`-l / --log`)

State-change events are appended to a plain-text file with ISO timestamps:

```
2026-03-06T14:22:10  [8.8.8.8]  OK              14.2ms
2026-03-06T14:25:03  [8.8.8.8]  OUTAGE          entering recovery mode
2026-03-06T14:26:52  [8.8.8.8]  RECOVERED       outage 109s  lat=13.9ms
```

The file is safe to tail in a separate window while the monitor runs.

### Latency threshold warning (`--warn-ms`)

When the rolling average latency exceeds the threshold, the status changes to `HIGH LAT` (amber) — even if no packets are lost. Useful for catching degraded-but-connected states.

```bash
python3 ping_monitor.py 8.8.8.8 --warn-ms 50
```

The warning clears automatically when the average drops back below the threshold, and logs the transition both ways.

### Desktop alerts (`--alert`)

Sends a native desktop notification when an outage begins and when connectivity is restored:

- **macOS** — uses `osascript`
- **Linux** — uses `notify-send` (install `libnotify-bin` if not present)

```bash
python3 ping_monitor.py 8.8.8.8 --alert
```

### `--no-color`

Strips all ANSI color codes. The dashboard still redraws in place; only color is removed. Combine with `--log` for a clean record:

```bash
python3 ping_monitor.py 8.8.8.8 --no-color -l events.log
```

---

## New Status States

Two new status labels beyond v1.x:

| Label | Meaning |
|---|---|
| `HIGH LAT` | Pings succeeding but rolling avg latency exceeds `--warn-ms`. Clears automatically. |
| `RETRYING` | First ping failed; performing immediate retries (unchanged behavior, now visible as a distinct label). |

---

## Examples

```bash
# Defaults — same as running v1.4.1 from the root
python3 ping_monitor.py

# Cloudflare DNS, 5-second polling
python3 ping_monitor.py 1.1.1.1 -i 5

# Monitor gateway and two DNS servers simultaneously
python3 ping_monitor.py 192.168.1.1 8.8.8.8 1.1.1.1

# Warn on high latency, log events, send desktop alerts
python3 ping_monitor.py 8.8.8.8 --warn-ms 40 -l ~/ping.log --alert

# Aggressive monitoring: fast retries, short timeout
python3 ping_monitor.py 8.8.8.8 -i 5 -R 1 -r 3 -t 2
```

---

## Architecture Changes from v1.x

| Area | v1.4.1 (stable) | v2.0.0-beta.1 |
|---|---|---|
| Configuration | Constants at top of file | `argparse` CLI flags |
| Hosts | Single (hardcoded `TARGET`) | Multiple (positional args) |
| Threading | Single-threaded; countdown loop drives rendering | One thread per host; main thread is render loop |
| Log file | None | Optional append-only event log |
| Latency warning | None | `--warn-ms` rolling average threshold |
| Alerts | None | `--alert` via `osascript` / `notify-send` |
| Color control | Always on | `--no-color` flag |

The render loop now runs in the main thread, redrawing all hosts every second. Each host's monitor thread updates shared state protected by a single `threading.Lock`. Pings are always performed outside the lock to avoid blocking the renderer.

---

## Known Beta Limitations

- `--no-color` still emits the ANSI screen-clear escape (`\033[2J\033[H`). Redirecting stdout to a file will include these codes — pipe through `col -b` or `sed 's/\x1b\[[0-9;]*[a-zA-Z]//g'` to strip them.
- `--alert` on Linux requires `notify-send`. If it is absent the flag is silently ignored.
- With many hosts (5+) and a short terminal, the dashboard may overflow the screen height. Reduce `--graph-height` and `--max-log` to compensate.

---

## Reporting Issues

File bugs and feedback at <https://github.com/trunty/LocalHelper/issues>.
