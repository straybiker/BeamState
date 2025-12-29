# BeamState

A real-time network monitoring application that pings configured nodes and displays their status on a beautiful dashboard.

![BeamState Dashboard](frontend/public/logo.png)

## Features

- **Real-time Monitoring**: Async pinging with configurable intervals per group or node
- **Modern Dashboard**: Dark-themed UI showing node status, latency, and packet loss
- **Web-Based Configuration**: Add, edit, and remove groups and nodes directly from the UI
- **Flexible Storage**: Supports InfluxDB for production or JSON file logging for development
- **Bootstrap Config**: Optionally define initial network topology in `config.json` for automatic database seeding on startup
- **PWA Support**: Install as a mobile app for quick access

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, aioping, InfluxDB client
- **Frontend**: React, Vite, Tailwind CSS, Lucide icons
- **Database**: SQLite (local), InfluxDB (optional for metrics)
- **Deployment**: Docker Compose

## Architecture & Persistence

BeamState uses a **Hybrid Storage Strategy** to balance speed and usability:

1.  **`backend/data/beamstate.db` (The Engine)**:
    - A high-performance **Runtime Cache** using SQLite.
    - Used by the Pinger and API for fast, concurrent access and complex relationship queries.
    - Functions as the application's reliable "RAM".

2.  **`backend/config.json` (The Blueprint)**:
    - The **Human-Readable Source of Truth**.
    - All configuration changes made in the UI are immediately synced here.
    - Ensures **Persistence** and **Portability**: If the database is deleted or corrupted, the system rebuilds itself entirely from this file on startup.
    - You can back up or share this file to preserve your network topology.

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker (optional, for containerized deployment)

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/BeamState.git
   cd BeamState
   ```

2. **Start the Backend**
   ```bash
   cd backend
   pip install -r requirements.txt
   python -m uvicorn main:app --reload --port 8000
   ```

3. **Start the Frontend** (in a new terminal)
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. **Open the Application**
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Docker Deployment

```bash
docker-compose up -d
```

This starts:
- **Frontend**: http://localhost:3000
- **Backend**: http://localhost:8000
- **InfluxDB**: http://localhost:8086 (admin/adminpassword)

## Configuration

### config.json

Define your network topology in `backend/config.json`. The database syncs with this file on startup.

```json
{
    "groups": [
        {
            "id": 1,
            "name": "Infrastructure",
            "interval": 60,
            "packet_count": 1,
            "nodes": [
                {
                    "id": 1,
                    "name": "Router",
                    "ip": "192.168.1.1",
                    "interval": 30
                },
                {
                    "id": 2,
                    "name": "Switch",
                    "ip": "192.168.1.2"
                }
            ]
        }
    ]
}
```

| Field | Description |
|-------|-------------|
| `id` | Unique identifier (required for sync) |
| `name` | Display name |
| `interval` | Seconds between pings (group default or node override) |
| `packet_count` | Number of ping packets to send |
| `ip` | IPv4 address to ping |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `backend/data/beamstate.db` | SQLite database path |
| `LOG_FILE` | `backend/data/ping_logs.json` | JSON log file path |
| `INFLUXDB_URL` | - | InfluxDB URL (enables InfluxDB logging) |
| `INFLUXDB_TOKEN` | - | InfluxDB authentication token |
| `INFLUXDB_ORG` | - | InfluxDB organization |
| `INFLUXDB_BUCKET` | - | InfluxDB bucket name |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/status` | Current pinger status and all node results |
| GET | `/config/groups` | List all groups |
| POST | `/config/groups` | Create a new group |
| DELETE | `/config/groups/{id}` | Delete a group |
| GET | `/config/nodes` | List all nodes |
| POST | `/config/nodes` | Create a new node |
| PUT | `/config/nodes/{id}` | Update a node |
| DELETE | `/config/nodes/{id}` | Delete a node |

Full API documentation available at `/docs` when running the backend.

## Project Structure

```
BeamState/
├── backend/
│   ├── main.py           # FastAPI app entry point
│   ├── node_pinger.py    # Async ping loop
│   ├── models.py         # SQLAlchemy + Pydantic models
│   ├── database.py       # Database connection
│   ├── storage.py        # InfluxDB/JSON storage
│   ├── cleanup.py        # Config sync logic
│   ├── config.json       # Network topology definition
│   ├── routers/
│   │   └── config.py     # CRUD API routes
│   ├── data/
│   │   ├── beamstate.db  # SQLite database
│   │   └── ping_logs.json # JSON ping logs
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Config.jsx
│   │   │   └── Layout.jsx
│   │   ├── api.js
│   │   └── main.jsx
│   ├── public/
│   │   ├── logo.png
│   │   └── manifest.json
│   └── package.json
├── docker-compose.yml
└── README.md
```

## Screenshots

### Dashboard
Real-time status of all monitored nodes grouped by category.

### Configuration
Manage groups and nodes with sortable tables.

## Troubleshooting

### Pings not working?
- Ensure the backend is running with admin/root privileges (ICMP requires elevated permissions)
- On Windows, run PowerShell as Administrator
- On Linux/Docker, the container needs `NET_ADMIN` capability

### Multiple ping entries in logs?
- Check for zombie Python processes: `tasklist /FI "IMAGENAME eq python.exe"`
- Kill all with: `taskkill /F /IM python.exe`

### Frontend not connecting?
- Ensure backend is running on port 8000
- Check CORS settings in `backend/main.py`

## License

MIT License - feel free to use and modify.


## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
