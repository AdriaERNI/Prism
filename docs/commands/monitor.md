# prism monitor

Monitor IRIS instance CPU, memory, disk I/O, and process load in real
time. Fetches live metrics from the IRIS `/api/monitor` REST endpoint
(Prometheus/OpenMetrics format), computes a weighted 0–100 load score,
and renders a rich terminal dashboard with sparkline history graphs,
colored progress bars, and a summary score panel.

## Usage

```
prism monitor              # one-shot dashboard snapshot
prism monitor --watch 2   # live dashboard, refresh every 2 seconds
prism monitor --json       # machine-readable JSON output (no dashboard)
prism monitor --json --raw # JSON with all raw metric samples
prism monitor --compare    # take two snapshots (5s apart) and compare
```

## Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--watch` | `-w` | `0` | Live monitoring mode: refresh every N seconds. Use `0` for a single snapshot. |
| `--json` | — | `false` | Output machine-readable JSON instead of the dashboard UI. |
| `--raw` | — | `false` | Include all raw metric samples in JSON output (use with `--json`). |
| `--compare` | — | `false` | Take two snapshots (5s apart) and compare their load scores (JSON output). |

## Dashboard layout

The default output (no `--json` flag) renders a rich terminal dashboard:

```
╭──────────────────────────────────────────── Prism Monitor ────────────────────────────────────────────╮
│                                IRIS Monitor    09:55:38  │  571 metrics  │  0 alerts                   │
│ ╭───────────────────────── CPU ──────────────────────────╮╭──────────────────────── Memory ────────────────────────╮ │
│ │ ███████░░░░░░░░░░░░░ 35.0/100                          ││ ██████████░░░░░░░░░░ 50.0/100                          │ │
│ │   ▄                                                    ││   ▄                                                    │ │
│ │  CPU Usage  55.0 %                                     ││  Memory Used  70.0 %                                   │ │
│ ╰────────────────────────────────────────────────────────╯│  Page Space    5.0 %                                   │ │
│                                                           │  SMH Full      1.2 %                                   │ │
│                                                           ╰────────────────────────────────────────────────────────╯ │
│ ╭─────────────────────── Disk/IO ────────────────────────╮╭─────────────────────── Process ────────────────────────╮ │
│ │ ████████████░░░░░░░░ 60.0/100                          ││ █████░░░░░░░░░░░░░░░ 25.0/100                          │ │
│ │   ▄                                                    ││   ▄                                                    │ │
│ │  Reads      120.5 ops/s                                ││  Processes            27                               │ │
│ │  Writes      45.3 ops/s                                ││  Glo Seize  2.5 events/s                               │ │
│ │  Disk Full       12.0 %                                ││  WD Cycle        13.0 ms                               │ │
│ ╰────────────────────────────────────────────────────────╯╰────────────────────────────────────────────────────────╯ │
│ ╭─────────────────────────────────────────────────── Load Score ───────────────────────────────────────────────────╮ │
│ │ ████████░░░░░░░░░░░░ 42.5/100  │  Grade: MODERATE                                                                │ │
│ │ CPU 35.0   Mem 50.0   Disk 60.0   Proc 25.0                                                                      │ │
│ │ Avg 42.5  │  1m 42.5  5m 42.5  15m 42.5  →                                                                       │ │
│ │ Score: lower=better (0-100)  |  Trend: ↓ improving → stable ↑ worsening                                          │ │
│ ╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯ │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### Resource panels

Four panels show individual resource categories:

| Panel | Metrics shown | Unit |
|-------|--------------|------|
| **CPU** | CPU Usage (OS %) | `%` |
| **Memory** | Memory Used %, Page Space %, SMH Full % | `%` |
| **Disk/IO** | Reads, Writes, Disk Full % | `ops/s`, `%` |
| **Process** | Processes, Glo Seize, WD Cycle | `#`, `events/s`, `ms` |

Each panel contains:
- **Score bar** — a 0–100 load index for that category (`N.N/100`)
- **Sparkline** — ASCII graph showing the history of that category's score
- **Sub-metrics** — individual metric values with their units

### Load Score panel

The bottom panel shows:
- **Overall score** — weighted composite (0–100, lower is better)
- **Grade** — `IDLE`, `HEALTHY`, `MODERATE`, `LOADED`, or `CRITICAL`
- **Per-category numbers** — `CPU 35.0  Mem 50.0  Disk 60.0  Proc 25.0`
- **Averages** — SMA + EWMA (1m/5m/15m) with trend arrow
- **Helper text** — explains score direction and trend arrows

## Scoring model

The load score is a 0–100 composite index where **higher = more loaded**.
It is built from four equally-weighted categories (25% each):

| Category | Weight | Contributing IRIS metrics |
|----------|--------|---------------------------|
| CPU | 25% | `iris_cpu_usage` (OS %), `iris_cpu_pct{id=...}` (per-process) |
| Memory | 25% | `iris_phys_mem_percent_used`, `iris_page_space_percent_used`, `iris_smh_total_percent_full` |
| Disk/IO | 25% | `iris_phys_reads_per_sec`, `iris_phys_writes_per_sec`, `iris_db_latency`, `iris_disk_percent_full` |
| Process | 25% | `iris_process_count`, `iris_glo_seize_per_sec`, `iris_wd_cycle_time`, `iris_sql_active_queries` |

Within each category, each metric is **normalised** to 0–100 using a
saturation threshold. Missing or `NaN` metrics are treated as zero
(not penalised).

### Health grades

| Grade | Score range | Meaning |
|-------|------------|---------|
| `idle` | 0–9 | Instance is practically idle |
| `healthy` | 10–29 | Normal operation, plenty of headroom |
| `moderate` | 30–59 | Noticeable load, monitor closely |
| `loaded` | 60–79 | Heavy load, potential performance impact |
| `critical` | 80+ | Near saturation, investigate immediately |

### Averages and trend

In `--watch` mode, the Load Score panel shows:

- **Avg** — Simple Moving Average (SMA) of all stored overall scores
- **1m / 5m / 15m** — Exponentially Weighted Moving Averages (EWMA)
  with 1-minute, 5-minute, and 15-minute decay windows
- **Trend arrow** — compares 1m EWMA vs 5m EWMA:
  - `↓` improving (load falling)
  - `→` stable
  - `↑` worsening (load rising)

The EWMA interval is automatically derived from the actual time between
snapshots, so the averages are accurate regardless of the `--watch`
refresh rate.

## JSON output

Use `--json` for machine-readable output (pipeline integration, logging):

```bash
prism monitor --json | jq .score.overall
```

```json
{
  "timestamp": 1784796218.77,
  "score": {
    "overall": 7.54,
    "cpu": 4.0,
    "memory": 3.67,
    "disk": 20.47,
    "process": 2.02,
    "details": { ... }
  },
  "grade": "idle",
  "metrics": {
    "iris_cpu_usage": 8.0,
    "iris_phys_mem_percent_used": 10.0,
    ...
  },
  "metric_count": 571,
  "alerts_count": 0
}
```

Add `--raw` to include the full list of parsed metric samples:

```bash
prism monitor --json --raw | jq '.raw_metrics | length'
```

## Compare mode

Use `--compare` to take two snapshots 5 seconds apart and see which is
less loaded:

```bash
prism monitor --compare
```

Output includes both snapshots and a comparison dict with
`less_loaded`, `difference`, `winner_score`, `loser_score`, and
per-category `sub_scores`.

## Live monitoring

Use `--watch N` to refresh the dashboard every N seconds:

```bash
prism monitor --watch 2   # refresh every 2 seconds
prism monitor --watch 0.5  # refresh every 500ms
```

Press `Ctrl+C` to stop. If a transient HTTP error occurs during a
refresh cycle, the error is shown inline and monitoring continues on
the next cycle — the session is not killed.

## History

The dashboard maintains a ring buffer of up to 360 samples (1 hour at
10-second intervals). Sparkline graphs in each panel show the recent
trend. In `--watch` mode, history accumulates across refresh cycles.

## Architecture

```
src/prism/iris/monitor/
├── parser.py       Prometheus text exposition format parser
├── scorer.py       Load score computation, health grade, comparison
├── dashboard.py    Rich terminal dashboard (HistoryBuffer, sparklines, bars)
└── __init__.py     collect_snapshot() — orchestrates API → parse → score

src/prism/iris/api/monitor.py    GET /api/monitor/metrics and /alerts
src/prism/cli/commands/monitor.py  CLI command (dashboard, JSON, compare)
src/prism/mcp/monitor.py         MCP tool: monitor_system
```

## Related

- [`prism info`](info.md) — print IRIS server version and namespaces.
- [`prism serve`](serve.md) — start the MCP server (includes `monitor_system` tool).
- [MCP tools](../mcp/tools.md) — `monitor_system` tool reference.