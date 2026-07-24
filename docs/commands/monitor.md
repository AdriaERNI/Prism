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
│                          IRIS Monitor    09:55:38  │  571 metrics  │  0 alerts  │  8 users             │
│ ╭────────── CPU ──────────╮╭──────── Memory ────────╮╭──────── Disk/IO ────────────────────╮ │
│ │ ████░░░░░░░░░░░░░░ 35.0/100 ││ ██████░░░░░░░░░ 50.0/100 ││ █████░░░░░░░░░░ 25.0/100        │ │
│ │   ▄                         ││   ▄                     ││   ▄                            │ │
│ │  CPU Usage   55.0 %         ││  Memory Used  70.0 %    ││  DB Total     8.0 GB           │ │
│ │   WRTDMN      3.2 %         ││  Page Space    5.0 %    ││  DB Free   3072.0 MB           │ │
│ │   GARCOL      1.1 %         ││  SMH Used      1.2 %    ││  DB Max      18.0 GB           │ │
│ │                              ││  SMH Total     2.0 GB   ││  DB Latency    4.0 ms          │ │
│ │                              │╰─────────────────────────╯│  DBs               2           │ │
│ │                              │                           │  Reads     120.5 ops/s         │ │
│ │                              │                           │  Writes     45.3 ops/s         │ │
│ │                              │                           ╰────────────────────────────────╯ │
│ ╭──────── Process ────────╮╭──────── SQL/Tx ────────╮╭──────── License ────────────────────╮ │
│ │ █████░░░░░░░░░░░░░ 25.0/100 ││ ░░░░░░░░░░░░░░░ 0.0/100 ││ ░░░░░░░░░░░░░░░ 0.0/100        │ │
│ │                             ││                         ││                                │ │
│ │  Processes      27          ││  Active Q       5       ││  Lic Used       10             │ │
│ │  Glo Refs     150.0 /s      ││  Queries/s  120.0 /s    ││  Lic Avail      15             │ │
│ │  Glo Upd      30.0 /s       ││  Avg Runtime   0.0 s    ││  Lic Days       30 d           │ │
│ │  Glo Seize    2.5 events/s  ││  Open Tx        3       ││  Sessions        8             │ │
│ │  WD Cycle    13.0 ms        ││  Tx Avg Sec    0.5 s    ││  CSP Conn       15             │ │
│ │  Cache Eff    95.0 %        ││                         ││  CSP In-Use      5             │ │
│ │   1234 rundow 5000 cmd      ││                         ││                                │ │
│ │   5678 loop   3000 cmd      ││                         ││                                │ │
│ ╰─────────────────────────────╯╰─────────────────────────╯╰────────────────────────────────╯ │
│ ╭──────────────────────────────────────── Load Score ────────────────────────────────────────────────╮ │
│ │ ████████░░░░░░░░░░░░ 42.5/100  │  Grade: MODERATE                                              │ │
│ │ CPU 35.0   Mem 50.0   Disk 25.0   Proc 25.0                                                      │ │
│ │ Avg 42.5  │  1m 42.5  5m 42.5  15m 42.5  →                                                       │ │
│ │ Score: lower=better (0-100)  |  Trend: ↓ improving → stable ↑ worsening                          │ │
│ ╰────────────────────────────────────────────────────────────────────────────────────────────────────╯ │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### Resource panels

Six panels are arranged in a 3-column grid (two rows). The top row shows
scored resource categories with score bars and sparklines; the bottom row
includes scored and informational panels:

| Panel | Metrics shown | Unit | Scored |
|-------|--------------|------|--------|
| **CPU** | CPU Usage (OS %), top-3 process types by CPU % | `%` | Yes |
| **Memory** | Memory Used %, Page Space %, SMH Used %, SMH Total | `%`, `GB` | Yes |
| **Disk/IO** | DB Total, DB Free, DB Max, DB Latency, DB count, Reads/s, Writes/s | `GB`, `MB`, `ms`, `#`, `ops/s` | Yes |
| **Process** | Processes, Glo Refs, Glo Upd, Glo Seize, WD Cycle, Cache Eff, top-3 processes | `#`, `/s`, `events/s`, `ms`, `%`, `cmd` | Yes |
| **SQL/Tx** | Active Queries, Queries/s, Avg Runtime, Open Tx, Tx Avg Sec | `#`, `/s`, `s` | No |
| **License** | Lic Used, Lic Avail, Lic Days, Sessions, CSP Conn, CSP In-Use | `#`, `d` | No |

Each scored panel contains:
- **Score bar** — a 0–100 load index for that category (`N.N/100`)
- **Sparkline** — ASCII graph showing the history of that category's score
- **Sub-metrics** — individual metric values with their units

Informational panels (SQL/Tx, License) display a neutral score bar and no
sparkline — they show raw values for monitoring without contributing to the
load score.

The header shows the current time, total metric count, alert count, and
active user count (from `iris_csp_sessions` or `iris_license_consumed`).

### Dashboard metrics reference

Every value shown on the dashboard maps to an IRIS `/api/monitor` metric.
Below is the complete reference for each panel's sub-metrics.

#### CPU panel

| Label | IRIS metric | Unit | Description |
|-------|------------|------|-------------|
| CPU Usage | `iris_cpu_usage` | `%` | Percent of CPU usage for all programs on the operating system (not just IRIS) |
| CSPSRV | `iris_cpu_pct{id="CSPSRV"}` | `%` | CPU % used by the CSP Gateway server process (web requests) |
| WRTDMN | `iris_cpu_pct{id="WRTDMN"}` | `%` | CPU % used by the Write Daemon (flushes dirty buffers to disk) |
| GARCOL | `iris_cpu_pct{id="GARCOL"}` | `%` | CPU % used by the Garbage Collector (reclaims dead global nodes) |
| JRNDMN | `iris_cpu_pct{id="JRNDMN"}` | `%` | CPU % used by the Journal Daemon (writes journal entries) |
| Other types | `iris_cpu_pct{id="..."}` | `%` | ECPWorker, LICENSESRV, WDAUX, CSPDMN, ODBCSRC, Mirror* — shown by CPU % descending, top-3 only |

The per-process-type rows only appear when that process type is using CPU > 0%.

#### Memory panel

| Label | IRIS metric | Unit | Description |
|-------|------------|------|-------------|
| Memory Used | `iris_phys_mem_percent_used` | `%` | Percent of physical memory (RAM) currently in use by the OS |
| Page Space | `iris_page_space_percent_used` | `%` | Percent of maximum allocated page file / swap space used |
| SMH Used | `iris_smh_total_percent_full` | `%` | Percent of allocated shared memory heap in use by the IRIS instance |
| SMH Total | `iris_smh_total` (KB → GB) | `GB` | Total shared memory allocated for the IRIS instance, converted from KB to GB |

SMH (Shared Memory Heap) is the memory IRIS uses for database cache, routine
buffer, and other shared structures. High SMH Used % means the cache is
under pressure — IRIS may need more allocated memory.

#### Disk/IO panel

| Label | IRIS metric | Unit | Description |
|-------|------------|------|-------------|
| DB Total | Sum of `iris_db_size_mb` ÷ 1024 | `GB` | Total size of all databases on this instance, summed across all databases and converted from MB to GB |
| DB Free | Sum of `iris_db_free_space` | `MB` | Total free space across all databases in MB (note: IRIS updates this metric once per day) |
| DB Max | Sum of `iris_db_max_size_mb` ÷ 1024 | `GB` | Maximum size all databases can grow to, summed and converted to GB |
| DB Latency | Average of `iris_db_latency` | `ms` | Average random-read latency across all databases in milliseconds — lower is better. High latency indicates slow disk I/O |
| DBs | Count of `iris_db_size_mb` samples | `#` | Number of databases on this instance |
| Reads | `iris_phys_reads_per_sec` | `ops/s` | Physical database blocks read from disk per second — high values mean disk I/O pressure |
| Writes | `iris_phys_writes_per_sec` | `ops/s` | Physical database blocks written to disk per second |

Database metrics are labeled by database name (e.g. `{id="USER",dir="/data/user/"}`).
The collector aggregates all labeled samples into the totals shown above.

#### Process panel

| Label | IRIS metric | Unit | Description |
|-------|------------|------|-------------|
| Processes | `iris_process_count` | `#` | Total number of active IRIS processes (integer count) |
| Glo Refs | `iris_glo_ref_per_sec` | `/s` | Global references per second — how many global (array) lookups are happening on local databases |
| Glo Upd | `iris_glo_update_per_sec` | `/s` | Global updates per second — SET and KILL commands to globals on local databases |
| Glo Seize | `iris_glo_seize_per_sec` | `events/s` | Global resource seizes per second — contention indicator. High values mean processes are fighting over the same global arrays |
| WD Cycle | `iris_wd_cycle_time` | `ms` | Write Daemon cycle time in milliseconds — how long the last write-daemon cycle took. High values (>2000ms) indicate disk I/O bottleneck |
| Cache Eff | `iris_cache_efficiency` | `%` | Cache hit ratio — global references vs physical reads/writes as a percent. High (90%+) means most data is served from cache, not disk |
| PID + routine | `iris_process_commands` + `iris_process` | `cmd` | Top-3 processes by ObjectScript command count. Shows PID, routine name (truncated to 8 chars), and total commands executed since process start |

The top-3 process rows show the processes with the highest command counts.
Each row shows the PID, the routine being executed (e.g. `MyClass.Method`
shown as `MyClass.`), and the total ObjectScript commands that process has
executed.

#### SQL/Tx panel (informational)

| Label | IRIS metric | Unit | Description |
|-------|------------|------|-------------|
| Active Q | `iris_sql_active_queries` | `#` | Number of SQL statements currently executing across all namespaces |
| Queries/s | `iris_sql_queries_per_second` | `/s` | Average number of SQL statements executed per second (per namespace, shown as total) |
| Avg Runtime | `iris_sql_queries_avg_runtime` | `s` | Average SQL statement runtime in seconds — high values indicate slow queries |
| Open Tx | `iris_trans_open_count` | `#` | Number of open (uncommitted) transactions on this instance |
| Tx Avg Sec | `iris_trans_open_secs` | `s` | Average duration of currently open transactions in seconds — long open transactions cause lock contention and journal bloat |

SQL metrics are labeled by namespace (e.g. `{id="USER"}`). The dashboard
shows the value from the first namespace or the aggregate.

#### License panel (informational)

| Label | IRIS metric | Unit | Description |
|-------|------------|------|-------------|
| Lic Used | `iris_license_consumed` | `#` | Number of IRIS licenses currently in use — each connected user or application consumes one license seat |
| Lic Avail | `iris_license_available` | `#` | Number of license seats not currently in use. When this hits 0, new connections are refused |
| Lic Days | `iris_license_days_remaining` | `d` | Days before the IRIS license key expires. Plan renewal before this reaches 0 |
| Sessions | `iris_csp_sessions` | `#` | Currently active web (CSP) session IDs — represents logged-in web users |
| CSP Conn | Sum of `iris_csp_actual_connections` | `#` | Total current connections to this server by the Web Gateway, summed across all IP:port endpoints |
| CSP In-Use | Sum of `iris_csp_in_use_connections` | `#` | Connections actively processing a web request right now (subset of CSP Conn) |

CSP connection metrics are labeled by IP address and port
(e.g. `{id="127.0.0.1:52773"}`). The collector sums all labels into totals.

### Database aggregation

The IRIS `/api/monitor` endpoint exposes database metrics as labeled
Prometheus samples (one per database), e.g.:

```
iris_db_size_mb{id="USER",dir="/data/user"} 5120
iris_db_size_mb{id="DOCDB",dir="/data/docdb"} 3072
```

The collector aggregates these labeled metrics into summary values:

| Aggregated field | Computation | Unit |
|------------------|-------------|------|
| `db_total_size_gb` | Sum of all `iris_db_size_mb` ÷ 1024 | GB |
| `db_total_free_mb` | Sum of all `iris_db_free_space` | MB |
| `db_total_max_gb` | Sum of all `iris_db_max_size_mb` ÷ 1024 | GB |
| `db_avg_latency_ms` | Average of all `iris_db_latency` | ms |
| `db_count` | Count of `iris_db_size_mb` samples | # |

Similarly, `iris_csp_actual_connections` and `iris_csp_in_use_connections`
are summed across all IP:port labels, and `iris_cpu_pct{id=...}` is extracted
into a per-process-type dict. These aggregations are available in the
`aggregated` field of `MonitorSnapshot` and in `--json` output.

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
| Process | 25% | `iris_process_count`, `iris_glo_seize_per_sec`, `iris_wd_cycle_time`, `iris_sql_active_queries`, `iris_trans_open_count` |

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
  "alerts_count": 0,
  "aggregated": {
    "db_total_size_gb": 8.0,
    "db_total_free_mb": 3072.0,
    "db_total_max_gb": 18.0,
    "db_avg_latency_ms": 4.0,
    "db_count": 2,
    "cpu_by_type": {"WRTDMN": 3.2, "GARCOL": 1.1},
    "top_processes": [{"pid": 1234, "commands": 5000, ...}],
    "csp_total_connections": 15.0,
    "csp_in_use_connections": 5.0,
    "smh_total_gb": 2.0
  }
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