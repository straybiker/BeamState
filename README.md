<p align="center">
   <img src="frontend/public/logo_transparant.png" alt="BeamState Logo" width="150"> 
</p>

# BeamState Network Monitor

Self-hosted network monitoring for a home lab. BeamState pings your devices, collects SNMP metrics from them, alerts you when something breaks or degrades, and keeps the history so you can tell which device is unreliable.

It asks each device what it can actually report rather than assuming, which matters once a network mixes routers, switches, access points, servers and printers: they rarely expose the same OIDs.

## Features

- **Reachability monitoring**: Async ICMP and SNMPv2c checks with per-group and per-node intervals, packet counts and retry limits.
- **Metric collection**: Interface traffic and errors, CPU, memory, load, temperature, storage and uptime, each on its own collection interval.
- **Device capability probing**: One click asks a device which metrics it supports and discovers its sensors, disks and interfaces **by name**. The configuration screen then hides what the device cannot answer.
- **Five node states**: UP, DEGRADED, PENDING, DOWN and PAUSED. A reachable device with a metric out of range is degraded, not down.
- **Alerting that stays quiet**: Pushover and generic JSON webhook, consecutive-sample confirmation, hysteresis, storm throttling, parent dependencies, recovery and reboot messages, maintenance mode.
- **History and reliability**: Every state change is persisted. Availability, downtime and flap counts per node over 24 hours and 30 days.
- **Metric history**: Short-term samples in SQLite drive sparklines on the Metrics page. Optional InfluxDB for long-term trends and Grafana.
- **Live dashboard**: Server-sent events push each completed check, with polling as a fallback.
- **Network discovery**: Scan a subnet for ICMP and SNMP devices and import them into a group.
- **Heartbeat**: Deadman ping to Healthchecks.io, Uptime Kuma or Home Assistant, so you notice when BeamState itself stops.
- **Backup by design**: SQLite is the source of truth; `config.json` is a continuously rewritten export you can copy to another host.

## Screenshots

### Dashboard
![Dashboard View](screenshots/dashboard.png)
*Node status, latency and availability per node, grouped by network segment*

### Metrics
![Metrics Dashboard](screenshots/snmp_metrics.png)
*Live SNMP and ICMP metrics with sparklines from the short-term history*

## Quick Start (Windows)

For local development on Windows, use the provided PowerShell script.

1. **Clone the repository**
   ```bash
   git clone https://github.com/straybiker/BeamState.git
   cd BeamState
   ```

2. **Create the configuration file**
   ```bash
   cd backend
   cp config.json.example config.json
   cd ..
   ```
   Everything in it can also be set from the UI later. `config.json` holds secrets (InfluxDB and Pushover tokens) and is gitignored.

3. **Start the application**
   ```powershell
   .\start-app.ps1
   ```
   Starts Uvicorn on port 8000 and Vite on port 5173, after freeing those two ports. Administrator rights are only needed if ICMP raw sockets are blocked on your Windows build.

4. **Open it**
   - Frontend: [http://localhost:5173](http://localhost:5173)
   - API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Docker Deployment

For a containerised deployment, for example in a Proxmox LXC. Both containers carry healthchecks and the frontend waits for a healthy backend.

### 1. Installation

```bash
git clone https://github.com/straybiker/BeamState.git
cd BeamState
cp backend/config.json.example backend/config.json
docker compose up -d --build
```

Create `backend/config.json` **before** the first start. Docker bind-mounts that exact path, so if the file does not exist Docker creates a *directory* with that name and the backend cannot read or write it. Check with `ls -ld backend/config.json`; a leading `d` means this happened.

Sizing: about 1.5 GB of free disk is needed to build both images. A 4 GB root disk is tight, since the two builds run in parallel.

### 2. Upgrading

Run from the repository directory inside the LXC.

```bash
# 1. Back up the database and config
docker exec beamstate-backend python -c "import sqlite3; s=sqlite3.connect('/app/data/beamstate.db'); d=sqlite3.connect('/app/data/beamstate.backup.db'); s.backup(d); d.close()"
cp backend/config.json backend/config.json.bak

# 2. Get the latest code
git pull

# 3. Rebuild and restart
docker compose up -d --build --force-recreate

# 4. Verify
docker compose ps                 # both containers "healthy" within about a minute
docker compose logs -f backend    # Ctrl+C stops following
```

Schema migrations run automatically at startup. Nothing has to be done to the database by hand.

Roll back with the backups from step 1:

```bash
docker compose down
cp backend/data/beamstate.backup.db backend/data/beamstate.db
cp backend/config.json.bak backend/config.json
git checkout <previous-tag>
docker compose up -d --build --force-recreate
```

If a build fails with **no space left on device**, reclaim it with `docker builder prune -f` and `docker image prune -f`, or grow the container disk from the Proxmox host with `pct resize <vmid> rootfs +4G`.

### 3. Post-upgrade checklist

Only relevant when coming from a release older than the one named.

**From before v1.2.0**
1. Open **Configuration → Metrics**, select each SNMP node and press **Probe device**. This discovers what each device supports and names its sensors, disks and interfaces.
2. Enable SNMP on nodes that have metrics configured but SNMP switched off. Those metrics were never collected; both the Metrics dashboard and the config screen now flag them.
3. Review the new Net-SNMP metrics if you run a UDM Pro, Pi-hole, NAS or any Linux host. See [Which system metrics work on which device](#which-system-metrics-work-on-which-device).

**From before v1.1.0**
1. Expect `Import policy: config.json modified after last export, importing` in the log once. The old-format file is imported and rewritten with `exported_at` and metric configuration. Later restarts skip it.
2. Re-enter group-level SNMP settings under **Configuration → Groups**. Older releases reset them on every restart; they persist now.
3. Set **Samples** to 2 or 3 on noisy metrics such as ICMP latency. Existing metrics keep 1, which alerts on a single spike.
4. Nodes with a metric out of range now show **DEGRADED** instead of DOWN. Review thresholds tuned around the old behaviour.
5. Optionally enable the webhook channel and heartbeat under **Configuration → Settings**.

### 4. Access

- **Frontend**: `http://<YOUR_IP>:3000`
- **Backend API**: `http://<YOUR_IP>:8000`, Swagger at `/docs`

The API has no authentication yet, and node endpoints return SNMP community strings. Keep both ports on the LAN or behind a reverse proxy that authenticates.

### 5. Data Persistence

The database and the configuration file live on the host through bind mounts, so they survive a rebuild.

| Host path | Contents | Role |
|---|---|---|
| `backend/data/beamstate.db` | groups, nodes, dependencies, metric config, capabilities, interfaces, state history, metric samples | **source of truth** |
| `backend/config.json` | export of the topology and metric config, plus `app_config` (settings and secrets) | mirror and backup, rewritten after every change |
| `backend/data/alert_states.json` | active metric alert levels | runtime state |
| `backend/data/system.log*`, `logs.json` | application log (rotating, 5 MB × 3) and monitoring data log | runtime state |

- **Fresh volume or lost database**: the import policy sees an empty database and rebuilds groups, nodes, dependencies and metric configuration from `config.json`. Only the history tables are lost.
- **Keep the mount on local disk.** SQLite is unreliable on NFS or SMB because of file locking. A bind mount inside an LXC is fine.
- **Backups**: a Proxmox snapshot covers everything. To copy the database while the container runs, use SQLite's online backup as in the upgrade steps above, so you never copy a half-written file.
- **Size**: metric samples grow fastest, roughly 1,500 rows per metric per day, pruned after `history.metric_retention_days` (default 3). Expect tens of megabytes.
- **InfluxDB**: when enabled, time-series data is stored on your InfluxDB instance, not in these containers.

## Configuration

Almost everything is configurable from the UI under **Configuration**. The tabs are Nodes, Metrics, Groups and Settings.

### Network topology

The **database is the source of truth**. `config.json` is an export of it: groups, nodes, dependencies and metric configuration, rewritten after every change in the UI and at startup. Treat the file as a portable backup.

- `GET /config/export` returns the same document without secrets.
- `POST /config/import` upserts a document. Nothing is deleted. Nodes carrying a `metrics` list get their metric configuration replaced, matched to definitions by **name** rather than id, so an export moves between installs.
- At startup, `should_import_config()` in `backend/cleanup.py` decides whether the file is imported before the export runs. It imports in three cases: the file contains `"import": true` (consumed on the next start), the database has no groups yet, or the file was modified more than 5 seconds after its `exported_at` timestamp, meaning a hand edit or a restored backup. A file without `exported_at` is imported once and rewritten in the new format.

Per node you can set the interval, packet count, retry limit, protocols, SNMP community and port, alert priority, and a **parent** whose outage suppresses this node's alerts. Empty fields inherit the group value.

### Application settings (`app_config`)

| Section | Keys | Purpose |
|---|---|---|
| `influxdb` | `enabled`, `url`, `org`, `bucket`, `token` | Long-term time series for Grafana |
| `logging` | `file_enabled`, `file_path`, `retention_lines`, `log_level` | Monitoring data log and application log level |
| `pushover` | `enabled`, `token`, `user_key`, `priority`, `message_template`, `throttling_enabled`, `alert_threshold`, `alert_window`, `maintenance_mode` | Push notifications and storm throttling |
| `webhook` | `enabled`, `url` | Generic JSON notifications |
| `alerting` | `notify_recovery`, `notify_reboot` | Whether recovery and reboot messages are sent |
| `heartbeat` | `enabled`, `url`, `interval` | Deadman ping proving BeamState is alive |
| `history` | `retention_days`, `metric_retention_days` | State event and metric sample retention |

Secrets and any URL that can embed a token are returned as `***REDACTED***` by `GET /config/app` and preserved when you save without changing them.

### Node states

| State | Meaning |
|---|---|
| UP | Reachable, all metrics within thresholds |
| DEGRADED | Reachable, at least one metric in WARNING or CRITICAL |
| PENDING | A reachability check failed, retrying at one third of the interval |
| DOWN | Retries exhausted |
| PAUSED | Node or group disabled |

A node is reachable only when **all** its configured protocols succeed. Metric alerts can never make a node DOWN, only DEGRADED, so DOWN unambiguously means unreachable.

### Notifications

Both channels are configured under **Settings** and can be active at once. Maintenance mode suppresses every channel.

- **Pushover**: user key and API token, priority -2 (lowest) to 2 (emergency, retried every 60 s for 1 h). A per-node priority overrides the global value.
- **Webhook**: JSON POST to any URL, which covers ntfy, Discord, Home Assistant and n8n. Payload: `source`, `event`, `title`, `message`, `priority`, `timestamp`, plus context such as `node`, `ip`, `group`, `status`, or the metric name, value and unit.

| `event` | Sent when |
|---|---|
| `node_down` | Retries exhausted |
| `node_up` | A DOWN node is reachable again, with the downtime |
| `node_reboot` | SNMP uptime dropped, meaning the device restarted |
| `metric_warning`, `metric_critical` | A metric crossed a threshold and the sample count was met |
| `metric_resolved` | A metric returned to normal |
| `alert_storm` | Throttling engaged, one summary instead of many alerts |

Noise controls, in the order they apply:

1. **Consecutive samples**: an alert raises only after N breaching samples in a row.
2. **Hysteresis**: a 5 % band keeps a metric alerting until it is clearly back in range.
3. **Cooldown**: 60 seconds between messages for the same metric.
4. **Parent dependency**: while a parent is DOWN, the child's DOWN alert and its recovery message are suppressed.
5. **Storm throttling**: more than X alerts within Y seconds pauses individual alerts and sends one summary.

### Metric alerts

Per metric: a condition (above or below), warning and critical thresholds, and **Samples**, the number of consecutive breaching samples before the alert raises. Recovery is immediate. Metrics of a paused node or group raise nothing.

### Reliability and reboots

- `GET /trace/availability?windows=24,720` returns availability, downtime and DOWN count per node from the state history. PENDING is not counted as downtime and PAUSED time is excluded from the window. The dashboard shows the 24-hour figure beside each node; the Trace page ranks the least available.
- SNMP nodes report **reboots**. A `sysUpTime` lower than the previous reading raises `node_reboot` with the previous uptime, which catches restarts that fall between two checks. Counter wrap at 497 days is not mistaken for a reboot.

### History

- **State events**: every transition is written to `state_events` and served by `GET /trace/events?limit=&node_id=&hours=`. Retention in days is set under Settings, 0 keeps everything.
- **Metric samples**: every processed value is kept in `metric_samples`. `GET /metrics/history?hours=6&points=48` returns bucketed averages that feed the sparklines. InfluxDB remains the right choice for long-term trends.

### Live dashboard

The dashboard subscribes to `GET /status/stream`. It receives a snapshot on connect, one message per completed check, and a `config` event when groups, nodes or settings change. Polling every 15 seconds is the fallback while the stream is down; the header badge shows which mode is active.

### Heartbeat

Set a ping URL under Settings, from Healthchecks.io, an Uptime Kuma push monitor or a Home Assistant webhook. BeamState sends a GET on the configured interval and the receiving service alerts you when the pings stop. Set the receiver's grace period to two or three times the interval so a container restart is not a false alarm.

## SNMP Metrics

### Probe device

There is no set of system OIDs that works everywhere, so BeamState asks each device instead of guessing. Under **Configuration → Metrics**, pick a node and press **Probe device**:

- Every scalar metric is tested in a single multi-varbind SNMP GET. Anything the device answers is supported.
- Every indexed metric has its instance name column walked, so sensors, disks, storage and interfaces arrive **named**. You tick "temp-cpu" instead of typing index 4.
- The result is stored per node. The configuration screen lists only supported metrics and collapses the rest behind *Not supported by this device*, which stays expandable in case a firmware update adds an OID.
- Each row shows the reading seen while probing, so a sensor stuck at 0 is obvious.
- **Enable all** switches on every supported scalar system metric in one click.

Probing takes 0.1 to 0.7 seconds on UniFi hardware, longer on slow devices such as printers. Re-probe after a firmware update or when interfaces change. A node that has never been probed lists every metric, as before.

### Which system metrics work on which device

Interface metrics come from the standard IF-MIB and work everywhere. System metrics do not. This is what probing found across one home lab:

| Device family | Supported system metrics | Source MIB |
|---|---|---|
| UDM Pro, and any Net-SNMP Linux host (Pi-hole, NAS, Proxmox, Docker host) | `Linux Load (1m/5m/15m)`, `CPU Idle/User/System (Net-SNMP)`, `Linux Mem Total/Available/Buffers/Cached`, `Linux Swap Total/Available`, `Sensor Temperature`, `TCP Connections`, `System Uptime` | UCD-SNMP-MIB (1.3.6.1.4.1.2021), temperature from its lm-sensors table |
| UniFi switches and access points (USW, UAP, U6) | `CPU (UniFi)`, `Linux Load (1m/5m/15m)`, `Linux Mem Total/Available/Buffers/Cached`, `Linux Swap Total/Available`, `System Uptime` | HOST-RESOURCES for CPU, UCD for the rest. No temperature sensor |
| EdgeSwitch | `Temperature`, `CPU Load (%)`, `TCP Connections`, `System Uptime` | Broadcom (1.3.6.1.4.1.4413) |
| Printers, Windows, other generic hosts | `Storage Used`, `System Uptime`, `TCP Connections` | HOST-RESOURCES-MIB (1.3.6.1.2.1.25) |

Notes:

- **The UDM Pro reports no CPU percentage.** Use `CPU Idle (Net-SNMP)` with the condition set to **below**, for example warn under 30 % idle, or add `CPU User` and `CPU System`. Both `CPU Utilization` and `CPU (UniFi)` return "no such object" on it.
- **The UDM Pro reports no disk usage.** It exposes neither `hrStorage` nor `dskTable`. `Disk Used (%)` and `Storage Used` work on Net-SNMP hosts where `disk` is configured in `snmpd.conf`.
- **Temperature sits in a different place per family.** EdgeSwitch uses the Broadcom `Temperature` OID. Net-SNMP hosts including the UDM Pro use `Sensor Temperature` from the lm-sensors table, which needs a sensor index; probing discovers and names them. On a UDM Pro expect `temp-CPU`, `temp-Local`, `temp-PHY` and `temp-cpu`, the last being the SoC package and the hottest. Sensors reading 0 are unpopulated.
- **UniFi access points must have SNMP enabled in the UniFi controller** as well as in BeamState.

### Defining custom metrics (`snmp.json`)

Definitions live in `backend/snmp.json` and are seeded into the database at startup, matched by `name`. Editing a definition updates it in place; adding one makes it available everywhere.

| Field | Purpose |
|---|---|
| `name` | Display name and the key used for seeding and for import matching. Must be unique |
| `oid_template` | The OID. Use `{index}` for a table column |
| `metric_type` | `gauge` for a value, `counter` for something that only increases. Counters are converted to a per-second rate |
| `unit` | Controls formatting and rate conversion, see the table below |
| `category` | `interface` puts the metric in the interface section, anything else in system metrics |
| `device_type` | Informational only |
| `metric_source` | `snmp` (default) or `icmp` for internally computed metrics |
| `requires_index` | `true` when the OID needs an instance index |
| `instance_oid` | The table column holding instance **names**. Probing walks it to offer named instances. Optional, but without it the index must be typed by hand |

Units the UI understands:

| `unit` | Rendered as |
|---|---|
| `bytes` | KB, MB or GB. As a `counter`, converted to bits per second and shown as Kbps, Mbps or Gbps |
| `kbytes` | Same, scaled from kilobytes |
| `percent` | `42.5%` |
| `celsius` | `66°C` |
| `millicelsius` | Divided by 1000, `48°C` |
| `load_x100` | Divided by 100, `2.04` |
| `ms` | `5.33 ms` |
| `timeticks` | Hundredths of a second turned into `11d 18h` |
| `status` | IF-MIB operational status name, `Up (1)` |
| `connections`, `errors`, `allocation_units` | Plain number |

Anything else is shown as a number rounded to two decimals.

Example of an indexed metric with instance discovery:

```json
{
    "name": "Cisco Temperature",
    "oid_template": "1.3.6.1.4.1.9.9.13.1.3.1.3.{index}",
    "instance_oid": "1.3.6.1.4.1.9.9.13.1.3.1.2",
    "metric_type": "gauge",
    "unit": "celsius",
    "category": "environment",
    "device_type": "cisco",
    "requires_index": true
}
```

To see what a device exposes before writing a definition, walk it from a shell: `snmpwalk -v2c -c <community> <ip> 1.3.6.1.4.1.2021` for the Net-SNMP tree, or `1.3.6.1.2.1.25` for HOST-RESOURCES.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| No **Probe device** button | SNMP is off for that node. Enable it under **Configuration → Nodes**. The screen now says so. |
| Metrics show `-` on the dashboard | Usually SNMP off on a node that still has metrics configured; an amber banner names it. Otherwise the device stopped answering that OID, so re-probe. |
| A metric was configured but shows nothing after a probe | It is listed under *Not supported by this device*. The device does not implement that OID. |
| Group SNMP settings reset on restart | Fixed in v1.1.0. Re-enter them once. |
| Container build fails, no space left | `docker builder prune -f`, then grow the disk with `pct resize <vmid> rootfs +4G`. |
| `config.json` is a directory | It did not exist at first start. Stop the stack, remove the directory, copy `config.json.example`, start again. |
| Version in the About card is stale | The version is baked in at build time. Rebuild with `--build` and hard-refresh the browser. |
| Alerts flap on latency spikes | Raise **Samples** to 2 or 3 for that metric. |

## API

Interactive docs at `/docs`. The endpoints most useful outside the UI:

| Endpoint | Purpose |
|---|---|
| `GET /status` | Every node's latest result |
| `GET /status/stream` | Server-sent events, one message per check |
| `GET /config/export`, `POST /config/import` | Move a topology between installs |
| `POST /metrics/probe/{node_id}` | Probe a device's capabilities |
| `GET /metrics/capabilities/{node_id}` | Stored probe result |
| `GET /metrics/current`, `GET /metrics/history` | Live values and bucketed history |
| `GET /trace/events`, `GET /trace/availability` | State history and uptime statistics |
| `GET /trace/stream` | Server-sent events for state changes |
| `POST /discovery/scan`, `POST /discovery/import` | Subnet discovery |

## Documentation

- [**Grafana Guide**](GRAFANA_GUIDE.md): dashboards and alerts on the InfluxDB data.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, pysnmp 7, ping3.
- **Frontend**: React, Vite, Tailwind CSS, Lucide Icons.
- **Database**: SQLite at `backend/data/beamstate.db`, override with the `DB_PATH` environment variable.
- **CI**: GitHub Actions runs the backend tests, frontend lint and build, and both Docker builds on every push and pull request.

## Development

```bash
cd backend && TESTING=1 python -m pytest tests -q
cd frontend && npm run lint && npm run build
```

`TESTING=1` switches the backend to an in-memory database and disables the monitor loop.

## Project Structure

```
BeamState/
├── backend/
│   ├── main.py              # App entry point, SSE status stream, retention loop
│   ├── monitor_manager.py   # Node state machine, alerts, reboot detection, heartbeat
│   ├── metrics_processor.py # Thresholds, sample counting, rates, metric history
│   ├── capability_probe.py  # Asks a device what it supports
│   ├── availability.py      # Uptime statistics from state history
│   ├── notifications.py     # Pushover, webhook, Notifier facade
│   ├── trace_manager.py     # State events, ring buffer and persistence
│   ├── discovery_engine.py  # Subnet scanning
│   ├── cleanup.py           # Import policy and config.json import
│   ├── utils.py             # Export to config.json
│   ├── storage.py           # App config, InfluxDB, monitoring data log
│   ├── snmp.json            # Metric definitions
│   ├── config.json          # Export of the database plus settings (gitignored)
│   ├── monitors/            # Ping, SNMP health check, SNMP collector
│   ├── routers/             # API endpoints
│   ├── migrations/          # Schema updates applied at startup
│   ├── tests/               # pytest suite
│   └── data/                # SQLite DB, alert state, logs (bind-mounted)
├── frontend/src/components/ # Dashboard, Metrics, Trace, Discovery, Config
├── .github/workflows/       # CI
├── docker-compose.yml
└── start-app.ps1            # Local dev startup (Windows)
```

## Roadmap

### Coverage
- [ ] **Service checks** - TCP port, HTTP status and DNS monitors next to ICMP and SNMP
- [ ] **API authentication** - Required before exposing the UI outside the LAN
- [ ] **SNMPv3** - Community strings travel in clear text today

### Notifications
- [ ] **Scheduled maintenance windows** - Per-group windows with a start and end time

### Configuration UI
- [ ] **Max retries and timeouts** - Expose in the UI; timeouts are fixed at 5 s today
- [ ] **Interface operational status alerts** - Alert on an up-to-down change by name instead of a numeric threshold

### Dashboard
- [ ] **Collapsible groups**
- [ ] **Drag and drop nodes between groups**
- [ ] **Mobile config layout** - The node table wraps badly on small screens

Release notes for what has already shipped are on the [releases page](https://github.com/straybiker/BeamState/releases).

## License

MIT License
