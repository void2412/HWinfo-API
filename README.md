# HWInfo64 Sensor API Server

A lightweight Python FastAPI server that reads hardware sensor data from HWInfo64's shared memory on Windows and exposes it as a JSON REST API with an HTML dashboard.

## Features

- **Real-time Sensor Data**: Reads CPU/GPU temperature, voltage, fan speed, power consumption, clock speeds via HWInfo64 shared memory (zero polling overhead after initial read)
- **REST API**: JSON endpoints for programmatic access with optional sensor type filtering
- **HTML Dashboard**: Live web UI showing all sensors grouped by type with min/max/avg statistics
- **Offline Detection**: Auto-detects when HWInfo64 is unavailable; dashboard auto-refreshes until reconnection
- **Service Deployment**: Windows service via NSSM with auto-start and persistent logging
- **No External Deps**: Uses Python stdlib (ctypes, mmap, struct) for Windows shared memory I/O
- **Production-Ready**: Pydantic v2 validation, comprehensive test suite (19 tests), secure error handling

## Tech Stack

- **Python 3.13+** with type hints
- **FastAPI** 0.115+ (async-capable)
- **Uvicorn** 0.30+ (production ASGI server)
- **Pydantic v2** (data validation & serialization)
- **pydantic-settings** (`.env` configuration)
- **Jinja2 3.1+** (HTML templating)
- **ctypes+mmap** (stdlib Windows shared memory reader)

## Quick Start

### Prerequisites

- Windows 10/11
- Python 3.13+
- HWInfo64 with **Settings → General → Shared Memory Support** enabled

### Installation

1. Clone or extract the project:
   ```bash
   cd C:\path\to\HWinfo-API
   ```

2. Create virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure (optional, defaults work for most):
   ```bash
   copy .env.example .env
   # Edit .env if needed (HOST, PORT, LOG_LEVEL)
   ```

5. Run locally:
   ```bash
   python main.py
   ```
   Dashboard: http://localhost:8000  
   API: http://localhost:8000/api/sensors

## API Endpoints

### GET /
**HTML Dashboard** — Live sensor table grouped by type  
Response: HTML (200 if online, with auto-refresh if offline)

Example:
```
GET http://localhost:8000/
```

### GET /api/sensors
**All Sensors (JSON)** — Array of sensor readings with optional filtering  
Query Parameters:
- `type` (optional): Filter by sensor type. Valid: `temperature`, `voltage`, `fan`, `current`, `power`, `clock`, `usage`

Response (200):
```json
[
  {
    "id": 1,
    "sensor_index": 0,
    "type": "temperature",
    "name": "CPU Package",
    "unit": "°C",
    "value": 65.5,
    "value_min": 30.2,
    "value_max": 85.1,
    "value_avg": 62.3
  },
  ...
]
```

Error (400) - Invalid type:
```json
{
  "error": "Unknown type 'invalid'",
  "valid_types": ["clock", "current", "fan", "power", "temperature", "usage", "voltage"]
}
```

Error (503) - HWInfo offline:
```json
{"error": "HWInfo64 is not running or shared memory is unavailable"}
```

Examples:
```bash
# All sensors
curl http://localhost:8000/api/sensors

# Only temperature
curl "http://localhost:8000/api/sensors?type=temperature"

# Only voltage
curl "http://localhost:8000/api/sensors?type=voltage"
```

### GET /health
**Health Check** — Server and HWInfo connection status  
Response (200):
```json
{
  "status": "ok",
  "sensor_count": 42
}
```

Response (503) - HWInfo offline:
```json
{"status": "hwinfo_offline"}
```

Example:
```bash
curl http://localhost:8000/health
```

## Configuration

Edit `.env` (create from `.env.example`):

```env
# Server binding
HOST=0.0.0.0              # Listen on all interfaces (for nginx/reverse proxy)
PORT=8000                 # HTTP port

# Logging
LOG_LEVEL=info            # debug, info, warning, error, critical
```

## Windows Service Deployment (NSSM)

Deploy as a Windows service that starts automatically on boot:

### Setup

1. **Prepare service directory** (example location):
   ```powershell
   mkdir C:\Services\HWInfoAPI
   Copy-Item -Recurse * C:\Services\HWInfoAPI\  # Copy project files
   cd C:\Services\HWInfoAPI
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```

2. **Install service** (run as Administrator):
   ```powershell
   # From project root where nssm.exe exists
   .\nssm.exe install HWInfoAPI "C:\Services\HWInfoAPI\.venv\Scripts\python.exe" "C:\Services\HWInfoAPI\main.py"
   
   # Set startup directory
   .\nssm.exe set HWInfoAPI AppDirectory "C:\Services\HWInfoAPI"
   
   # Optional: Redirect stdout/stderr to logs
   .\nssm.exe set HWInfoAPI AppStdout "C:\Services\HWInfoAPI\logs\stdout.log"
   .\nssm.exe set HWInfoAPI AppStderr "C:\Services\HWInfoAPI\logs\stderr.log"
   
   # Set to start automatically
   .\nssm.exe set HWInfoAPI Start SERVICE_AUTO_START
   ```

3. **Start the service**:
   ```powershell
   Start-Service HWInfoAPI
   ```

### Service Management

```powershell
# Check status
Get-Service HWInfoAPI

# Stop
Stop-Service HWInfoAPI

# Start
Start-Service HWInfoAPI

# Restart
Restart-Service HWInfoAPI

# View logs
Get-Content "C:\Services\HWInfoAPI\logs\*.log" -Tail 50

# Uninstall (stop first, then)
.\nssm.exe remove HWInfoAPI confirm
```

### Nginx Reverse Proxy (LAN)

Configure nginx to forward HTTP requests to the service:

```nginx
upstream hwinfo_api {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name hwinfo.local;  # or your LAN hostname

    location / {
        proxy_pass http://hwinfo_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Access via: http://hwinfo.local or http://<server-ip>

## HWInfo64 Configuration

**CRITICAL**: HWInfo64 shared memory must be enabled:

1. Open **HWInfo64**
2. **Settings → General → Shared Memory Support** — toggle ON
3. Click **OK**

Without this, the API returns 503 (offline). No restart required; the server will detect the change immediately.

## Project Structure

```
HWinfo-API/
├── main.py                 # FastAPI app, GET / dashboard
├── config.py               # Pydantic Settings (HOST, PORT, LOG_LEVEL)
├── requirements.txt        # pip dependencies
├── .env.example            # Configuration template
├── nssm.exe                # NSSM Windows service manager
├── hwinfo/
│   ├── __init__.py
│   ├── reader.py           # ctypes shared memory reader, parse_buffer()
│   └── models.py           # SensorReading Pydantic model, SENSOR_TYPE_NAMES
├── api/
│   ├── __init__.py
│   └── routes.py           # GET /api/sensors, GET /health
├── templates/
│   └── status.html         # HTML dashboard + offline page
├── tests/
│   ├── __init__.py
│   ├── test_reader.py      # parse_buffer() unit tests
│   └── test_routes.py      # FastAPI routes integration tests
├── logs/                   # Auto-created for service output
├── .env                    # Local override (git-ignored)
└── docs/
    ├── codebase-summary.md
    ├── system-architecture.md
    └── ...                 # Additional documentation
```

## Testing

Run all tests (no live HWInfo required — tests use synthetic buffers and mocks):

```bash
# Activate venv first
.venv\Scripts\activate

# Run tests
pytest

# With coverage
pytest --cov=hwinfo --cov=api
```

Test Coverage:
- **hwinfo/reader.py**: parse_buffer() with synthetic shared memory buffers
- **api/routes.py**: GET /api/sensors and GET /health with mocked read_sensors()
- **hwinfo/models.py**: Pydantic SensorReading validation (via integration tests)

## Troubleshooting

### "HWInfo64 is not running" (503 errors)

**Symptom**: Dashboard shows offline, `/health` returns 503

**Solution**:
1. Start HWInfo64
2. **Settings → General → Shared Memory Support** — ensure enabled
3. Refresh browser or call `/health` again

### Service won't start

**Symptom**: Service fails to start; check logs

**Solution**:
1. Verify Python path in NSSM config: `nssm edit HWInfoAPI` → check AppPath
2. Verify `.env` file syntax (should be `KEY=value`, one per line)
3. Check logs in `./logs/stdout.log` and `./logs/stderr.log`
4. Run `python main.py` manually in service directory to see errors

### "Address already in use" on port 8000

**Symptom**: `OSError: [Errno 48] Address already in use`

**Solution**:
1. Change PORT in `.env` to an unused port (e.g., 8001)
2. Or, kill process on 8000: `netstat -ano | findstr :8000`, then `taskkill /PID <pid> /F`

### Shared memory format error

**Symptom**: API returns empty sensors or parse errors in logs

**Solution**:
1. Confirm HWInfo64 version is recent (2020+)
2. Disable and re-enable shared memory in HWInfo64 settings
3. Restart HWInfo64

## Contributing

Contributions welcome. Please:
1. Write tests for new features
2. Run `pytest` before committing
3. Follow existing code style (type hints, clear naming)
4. Update docs if changing API or config

## License

See LICENSE file (if present) or contact the maintainer.

## Support

- **Docs**: See `./docs/` directory for architecture, codebase overview, and system design
- **Tests**: Run `pytest -v` for detailed test output
- **Logs**: Check `./logs/` directory when running as a service

---

**Last Updated**: May 2026  
**Python Version**: 3.13+  
**API Version**: 1.0.0
