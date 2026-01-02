# 📊 BeamState - Grafana Dashboard & Alerting Guide

This guide explains how to visualize your BeamState monitoring data in Grafana and set up alerts for node status and traffic events.

---

## 1. Setup Data Source

Before you can build dashboards, you need to connect Grafana to your InfluxDB instance where BeamState stores data.

1. **Log in to Grafana** (Default: `http://localhost:3000`, user: `admin`, pass: `admin`).
2. Navigate to **Connections** -> **Data Sources** -> **Add new data source**.
3. Select **InfluxDB**.
4. Configure the following settings:
   - **Query Language**: `Flux`
   - **URL**: `http://influxdb:8086` (or your InfluxDB IP)
   - **Organization**: `beamstate`
   - **Token**: _(The token from your `config.json` or `docker-compose.yml`)_
   - **Default Bucket**: `monitoring`
5. Click **Save & Test**. You should see "Datasource updated" and "3 buckets found".

---

## 2. Monitor Node Status

Create a panel to see which devices are UP or DOWN and alert when they fail.

### 📉 Step 1: Create Status Panel
1. Create a **New Dashboard**.
2. Click **Add visualization**.
3. Select your **InfluxDB** data source.
4. **Query** (Paste this Flux code):
   ```flux
   from(bucket: "beamstate")
     |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
     |> filter(fn: (r) => r["_measurement"] == "monitoring")
     |> filter(fn: (r) => r["_field"] == "status_code")
     // 1. Drop only the 'status' tag (legacy cleanup)
     |> drop(columns: ["status"])
     // 2. Get the latest value
     |> aggregateWindow(every: v.windowPeriod, fn: last, createEmpty: false)
     |> yield(name: "status")
   ```
   > **Note**: Encapsulating the query with `v.timeRangeStart` allows the dashboard time picker to control the data range.

5. **Visualization Settings** (Right panel):
   - **Visualization**: `State Timeline`
   - **Value mappings**:
     - `1` -> `UP` (Green)
     - `0` -> `DOWN` (Red)
   - **Standard options > Value options > Calculation**: `Last`
   - **Standard options > Display name**: `${__field.labels.node} - ${__field.labels.protocol}`
   > **Tip**: This will show separate lines for `icmp` and `snmp` for each node.
   > **Tip**: If `{{node}}` appears literally, use the syntax `${__field.labels.node}` which is required for some Grafana versions/visualizations.

### 🚨 Step 2: Create Status Alert
1. In the panel editor, click the **Alert** tab.
2. Click **Create alert rule from this panel**.
3. **Condition**: 
   - WHEN `last()` OF `A` IS BELOW `1`
4. **Set Evaluation Behavior**:
   - Evaluate every: `1m`
   - For: `2m`
5. **Configure Notifications**:
   - Add a contact point (e.g., Email, Slack, Discord) in Grafana Alerting settings.

---

## 3. Visualize Traffic Throughput

Traffic data is stored as **counters** (total bytes transferred). To see throughput (speed), we must calculate the **rate** of change.

### 📈 Step 1: Create Traffic Panel
1. Click **Add visualization**.
2. **Query** (Paste this Flux code):
   ```flux
   from(bucket: "beamstate")
     |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
     |> filter(fn: (r) => r["_measurement"] == "snmp_metrics")
     |> filter(fn: (r) => r["metric"] == "Traffic In (HC)" or r["metric"] == "Traffic Out (HC)")
     |> aggregateWindow(every: v.windowPeriod, fn: last, createEmpty: false)
     |> derivative(unit: 1s, nonNegative: true)
     |> map(fn: (r) => ({ r with _value: r._value * 8.0 })) // Convert Bytes to Bits
     |> yield(name: "throughput")
   ```
   > **Note**: If your devices don't support High Capacity (HC) counters, change `"Traffic In (HC)"` to `"Traffic In (Std)"`.

3. **Visualization Settings**:
   - **Visualization**: `Time Series`
   - **Unit**: `Bits/sec` (bps)
   - **Legend**: `{{node}} - {{metric}}`

### 🔔 Step 2: Create High Traffic Alert
1. Create a new alert rule.
2. **Query**: Same as above, but filter for a specific node if needed.
3. **Condition**:
   - WHEN `last()` OF `A` IS ABOVE `800000000` (800 Mbps)
4. **Set Evaluation Behavior**:
   - Evaluate every: `1m`
   - For: `5m` (Sustained traffic)

---

## 4. Useful Flux Queries for BeamState

Here are some ready-to-use snippets for your dashboards:

**Average Latency (Ping):**
```flux
from(bucket: "beamstate")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "monitoring")
  |> filter(fn: (r) => r["_field"] == "latency")
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
```

**Packet Loss (%):**
```flux
from(bucket: "beamstate")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "monitoring")
  |> filter(fn: (r) => r["_field"] == "packet_loss")
  |> aggregateWindow(every: 1m, fn: max, createEmpty: false)
```

**CPU Utilization (SNMP):**
```flux
from(bucket: "beamstate")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "snmp_metrics")
  |> filter(fn: (r) => r["metric"] == "CPU Utilization" or r["metric"] == "CPU (UniFi)")
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
```
