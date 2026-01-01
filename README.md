# BeamState
**Network Monitoring Solution**

A real-time network monitoring application that pings configured nodes, monitors SNMP metrics (Cpu, Memory, Traffic, etc.), and displays their status on a beautiful, dark-themed dashboard.

![BeamState Dashboard](frontend/public/logo_transparant.png)

## Features

- **Real-time Monitoring**: Async pinging with configurable intervals.
- **SNMP Support**: Monitor generic and specific OIDs (Interface Traffic, CPU, Memory, Uptime).
- **Customizable Metrics**: Define your own OIDs in `backend/snmp.json` and configure them via the UI.
- **Modern Dashboard**: Dark-themed UI showing node status, latency, SNMP availability, and detailed metrics.
- **Web-Based Configuration**: Add, edit, and remove groups/nodes/metrics directly from the UI.
- **Flexible Storage**: SQLite for configuration/cache, optional InfluxDB for time-series data.
- **Bootstrap Config**: Define initial topology in `config.json` for automatic seeding.

## Quick Start (Windows)

The easiest way to run the application locally on Windows is via the provided PowerShell script.

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/BeamState.git
   cd BeamState
   ```

2. **Start the Application**
   Open PowerShell as **Administrator** (required for ICMP Ping) and run:
   ```powershell
   .\start-app.ps1
   ```
   This script will:
   - Check and stop any existing instances on ports 8000/5173.
   - Start the Backend (Uvicorn) on port 8000.
   - Start the Frontend (Vite) on port 5173.

3. **Open the Application**
   - Frontend: [http://localhost:5173](http://localhost:5173)
   - Backend API: [http://localhost:8000](http://localhost:8000)
   - API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Configuration

### Network Topology (`config.json`)
The `backend/config.json` file acts as a blueprint. On startup, the database syncs with this file.

### SNMP Metrics (`snmp.json`)
Default SNMP metric definitions are stored in `backend/snmp.json`. You can add custom OIDs here.
- **oid_template**: Use `{index}` placeholder for interface metrics.
- **requires_index**: Set to `true` if the user needs to specify an index (e.g., Interface ID) or `false` for scalar values (like System Uptime).

Example:
```json
{
    "name": "Custom Temp",
    "oid_template": "1.3.6.1.4.1.9.9.13.1.3.1.3.{index}",
    "metric_type": "gauge",
    "unit": "celsius",
    "category": "environment",
    "device_type": "cisco",
    "requires_index": true
}
```

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, pysnmp-lextudio, ping3.
- **Frontend**: React, Vite, Tailwind CSS, Lucide Icons.
- **Database**: SQLite.

## Project Structure

```
BeamState/
├── backend/
│   ├── main.py             # App entry point
│   ├── snmp.json           # Default SNMP definitions
│   ├── config.json         # Network topology
│   ├── monitors/           # Ping and SNMP monitor logic
│   ├── routers/            # API endpoints
│   └── data/               # SQLite DB
├── frontend/
│   ├── src/components/     # React components
│   └── public/             # Assets
└── start-app.ps1           # Startup script
```

## License

MIT License
