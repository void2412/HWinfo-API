# HWInfo64 Sensor API — System Architecture

Comprehensive technical architecture covering component design, data flow, deployment topology, and system interactions.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                       │
│  CLIENT LAYER                                                         │
│  ┌──────────────────┐    ┌──────────────────────────────────┐       │
│  │ Browser          │    │ JSON API Consumer                │       │
│  │ (Dashboard HTML) │    │ (IoT, Apps, Scripts)             │       │
│  └────────┬─────────┘    └────────────┬─────────────────────┘       │
│           │                           │                              │
│           │ HTTP (GET /, /api/*, /health)                           │
│           │                                                           │
│           └──────────────┬────────────────────────────────┘          │
│                          │                                            │
│  NETWORK LAYER                                                        │
│                    ┌─────▼──────────────┐                            │
│                    │ Nginx Reverse Proxy│                            │
│                    │ (LAN, Port 80)     │                            │
│                    └─────┬──────────────┘                            │
│                          │                                            │
│                   HTTP   │   Port 8000                               │
│                          │                                            │
│  SERVICE LAYER          │                                            │
│                    ┌─────▼──────────────────────────┐                │
│                    │ HWInfoAPI Windows Service      │                │
│                    │ (NSSM Auto-Start)              │                │
│                    │ .venv\Scripts\python main.py   │                │
│                    └──────────┬─────────────────────┘                │
│                               │                                       │
│  APPLICATION LAYER           │                                       │
│                    ┌──────────▼─────────────┐                        │
│                    │ FastAPI App (main.py)  │                        │
│                    │ ├─ GET /                │                        │
│                    │ ├─ GET /api/sensors     │                        │
│                    │ └─ GET /health          │                        │
│                    └──────────┬──────────────┘                        │
│                               │                                       │
│  BUSINESS LOGIC LAYER        │                                       │
│                    ┌──────────▼──────────────┐                        │
│                    │ Sensor Reader Module    │                        │
│                    │ (hwinfo/)               │                        │
│                    │ ├─ read_sensors()       │                        │
│                    │ ├─ parse_buffer()       │                        │
│                    │ └─ Models (Pydantic)    │                        │
│                    └──────────┬───────────────┘                        │
│                               │                                       │
│  DATA ACCESS LAYER           │                                       │
│                    ┌──────────▼────────────────────────┐              │
│                    │ Windows Kernel API (ctypes)       │              │
│                    │ ├─ OpenFileMappingA()             │              │
│                    │ ├─ MapViewOfFile()                │              │
│                    │ └─ struct unpacking               │              │
│                    └──────────┬─────────────────────────┘              │
│                               │                                       │
│  HARDWARE LAYER             │                                       │
│                    ┌──────────▼───────────────────┐                  │
│                    │ Windows Named Shared Memory   │                  │
│                    │ Global\HWiNFO_SENS_SM2       │                  │
│                    │ ↓ populated by ↓             │                  │
│                    │ HWInfo64 (user-run)          │                  │
│                    │ ├─ Reads sensors             │                  │
│                    │ └─ Updates 40Hz (typical)    │                  │
│                    └──────────┬───────────────────┘                  │
│                               │                                       │
│                    ┌──────────▼──────────────────┐                   │
│                    │ Hardware                     │                   │
│                    │ ├─ CPU                       │                   │
│                    │ ├─ GPU                       │                   │
│                    │ ├─ Motherboard               │                   │
│                    │ ├─ Power Supply              │                   │
│                    │ ├─ Storage                   │                   │
│                    │ └─ Thermal Sensors           │                   │
│                    └──────────────────────────────┘                   │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### 1. Client Layer

**Role**: Users and systems consuming sensor data

**Components**:
- **Web Browser**: Accesses HTML dashboard at `GET /`
  - Auto-refreshes every 5 seconds if HWInfo offline
  - Displays sensors grouped by type in table format
  - Real-time updates (no polling; manual refresh only)

- **JSON API Consumers**: Scripts, IoT devices, monitoring systems
  - Calls `GET /api/sensors`, `GET /health`
  - Filters by sensor type: `?type=temperature`
  - Parses JSON responses

### 2. Network/Proxy Layer

**Role**: Route external requests to internal service (optional but recommended)

**Components**:
- **Nginx Reverse Proxy** (typical LAN setup):
  - Listens on `http://<server-ip>` or `http://hwinfo.local`
  - Forwards to `http://127.0.0.1:8000`
  - Adds headers: `X-Real-IP`, `X-Forwarded-For`
  - Decouples client from service port number

**Alternative**: Direct access to `http://localhost:8000` (single-machine usage)

### 3. Service Layer

**Role**: Application lifecycle and system integration

**Components**:
- **Windows Service (NSSM)**:
  - Service name: `HWInfoAPI`
  - Runs executable: `.venv\Scripts\python.exe main.py`
  - Start type: `SERVICE_AUTO_START`
  - Logs to: `./logs/stdout.log`, `./logs/stderr.log`
  - Restarts on crash (configurable)

**Benefits**:
- Starts automatically on Windows boot
- Runs in background (no console window)
- Managed via `Services` or `Start-Service` / `Stop-Service`
- Central logs location

### 4. Application Layer

**Role**: HTTP request handling and routing

**Components**:
- **FastAPI App** (main.py):
  - Framework: async ASGI application
  - Initialization: `FastAPI(title="...", version="...")`
  - Uvicorn server: `uvicorn.run(host=..., port=...)`

**Routes** (registered via APIRouter in api/routes.py):
- `GET /` — Dashboard (HTML)
- `GET /api/sensors` — Sensor list (JSON)
- `GET /health` — Status check (JSON)

**Request Flow**:
1. Uvicorn receives HTTP request
2. FastAPI routes to handler
3. Handler calls business logic
4. Response serialized (Pydantic → JSON or Jinja2 → HTML)
5. HTTP response sent

### 5. Business Logic Layer

**Role**: Sensor data processing, validation, filtering

**Components**:

#### hwinfo/reader.py — Core I/O
- `read_sensors()`: Public API; returns list or None
- `_read_raw()`: Windows-specific shared memory access
- `parse_buffer()`: Pure parsing function (testable)

#### hwinfo/models.py — Data Validation
- `SensorReading`: Pydantic model (strict typing)
- `SENSOR_TYPE_NAMES`: Type code mappings

#### api/routes.py — HTTP Handlers
- `get_sensors()`: Filter by type, validate, serialize
- `health()`: Status summary

#### config.py — Configuration
- `Settings`: Loads HOST, PORT, LOG_LEVEL from `.env`

#### templates/status.html — HTML Rendering
- Jinja2 template; renders sensor table
- Displays offline error with auto-refresh

### 6. Data Access Layer

**Role**: Low-level Windows API calls for shared memory

**Library**: ctypes (stdlib, no external deps)

**Key Functions**:
- `kernel32.OpenFileMappingA()` — Open shared memory handle
- `kernel32.MapViewOfFile()` — Get pointer to memory region
- `kernel32.UnmapViewOfFile()` — Release mapping
- `kernel32.CloseHandle()` — Close handle
- `struct.unpack()` — Binary parsing

**Error Handling**:
- Returns None if shared memory not found
- Validates magic number (0x57694853)
- Bounds-checks buffer size (max 64MB)

### 7. Hardware Layer

**Role**: Physical sensors on machine

**Sensors Provided by HWInfo64**:
- Temperature (CPU, GPU, motherboard, storage)
- Voltage (VCC, VCore, VDIMM, etc.)
- Fan speeds (CPU fan, case fans, GPU fan)
- Current (CPU, GPU)
- Power draw (CPU, GPU, system)
- Clock speeds (CPU, GPU)
- Usage/Load (CPU cores, GPU)
- Other (custom probes, etc.)

**Update Rate**: Typically 40 Hz (HWInfo64 setting)

---

## Data Flow Diagrams

### Request Flow: GET /api/sensors?type=temperature

```
Client Request
│
└─ GET /api/sensors?type=temperature
   │
   ├─ Query params: {"type": "temperature"}
   │
   └─→ api/routes.py :: get_sensors()
      │
      ├─ Call: read_sensors()
      │  │
      │  └─→ hwinfo/reader.py :: read_sensors()
      │     │
      │     ├─ Call: _read_raw()
      │     │  │
      │     │  └─→ Windows API
      │     │     ├─ OpenFileMappingA("Global\\HWiNFO_SENS_SM2")
      │     │     ├─ MapViewOfFile(handle, ...)
      │     │     ├─ ctypes.c_char * size from address
      │     │     ├─ UnmapViewOfFile(ptr)
      │     │     └─ CloseHandle(handle)
      │     │     Return: bytes or None
      │     │
      │     └─ If data is None: Return None
      │     └─ Else: Call parse_buffer(data)
      │        │
      │        └─→ hwinfo/reader.py :: parse_buffer()
      │           ├─ struct.unpack header
      │           ├─ Loop entries (idx=0 to count-1)
      │           │  ├─ Unpack entry at offset
      │           │  ├─ Decode strings (UTF-8 fallback)
      │           │  ├─ Create SensorReading
      │           │  └─ Append to list
      │           └─ Return list[SensorReading]
      │
      ├─ Check: sensors is None?
      │  ├─ Yes: Return 503 {"error": "..."}
      │  └─ No: Continue
      │
      ├─ Validate type
      │  ├─ Normalize: type.lower()
      │  ├─ Check: type in _VALID_TYPES?
      │  └─ No: Return 400 {"error": "Unknown type '...'",...}
      │
      ├─ Filter: sensors = [s for s in sensors if s.type == type]
      │
      └─ Serialize: [s.model_dump() for s in sensors]
         │
         └─ Response: JSON list + 200 OK
            │
            └─→ Client receives
               [
                 {"id": 1, "sensor_index": 0, "type": "temperature", ...},
                 {"id": 2, "sensor_index": 1, "type": "temperature", ...}
               ]
```

### Sensor Reading Structure in Memory

```
Shared Memory Layout (Global\HWiNFO_SENS_SM2)
┌──────────────────────────────────────────────────────┐
│                                                        │
│  HEADER (44 bytes)                                   │
│  ├─ [0-3]   uint32 magic         (0x57694853)        │
│  ├─ [4-7]   uint32 version                           │
│  ├─ [8-11]  uint32 version2                          │
│  ├─ [12-19] int64  last_update_ts                    │
│  ├─ [20-23] uint32 sensor_offset      ┐              │
│  ├─ [24-27] uint32 sensor_size        ├─ Metadata    │
│  ├─ [28-31] uint32 sensor_count       │              │
│  ├─ [32-35] uint32 entry_offset   ┐   │              │
│  ├─ [36-39] uint32 entry_size     ├─ Entry array     │
│  └─ [40-43] uint32 entry_count    │   │              │
│                                    ▼   ▼              │
│  ENTRIES (entry_count × entry_size bytes)            │
│  ├─ Entry[0]                                          │
│  │  ├─ [0-3]   uint32 type                           │
│  │  ├─ [4-7]   uint32 sensor_index                   │
│  │  ├─ [8-11]  uint32 id                             │
│  │  ├─ [12-139]   char[128] name_orig                │
│  │  ├─ [140-267]  char[128] name_user                │
│  │  ├─ [268-283]  char[16]  unit                     │
│  │  ├─ [284-291]  double value           ┐           │
│  │  ├─ [292-299]  double value_min       ├─ Stats    │
│  │  ├─ [300-307]  double value_max       │           │
│  │  └─ [308-315]  double value_avg       ▼           │
│  │  └─ [316-319]  [padding / reserved]               │
│  │                                                    │
│  ├─ Entry[1]                                         │
│  ├─ ...                                              │
│  └─ Entry[N-1]                                       │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Dashboard HTML Rendering Flow

```
GET /
│
└─→ main.py :: dashboard()
   │
   ├─ Call: read_sensors() → list[SensorReading] or None
   │
   ├─ If None: grouped = {}; online = False
   │ Else:
   │  ├─ Group by type:
   │  │  grouped = {
   │  │    "temperature": [SensorReading, ...],
   │  │    "voltage": [SensorReading, ...],
   │  │    ...
   │  │  }
   │  └─ online = True
   │
   └─ Render template:
      │
      └─→ templates/status.html
         │
         ├─ {% if online %}
         │  ├─ For each group:
         │  │  ├─ <div class="section">
         │  │  │  ├─ <h3>{{ group_name }}</h3>
         │  │  │  └─ <table>
         │  │  │     ├─ <thead>
         │  │  │     └─ <tbody>
         │  │  │        └─ For each sensor:
         │  │  │           └─ <tr>{{ sensor_data }}</tr>
         │  │  └─ </div>
         │  └─ <!-- If no groups: empty but valid HTML -->
         │
         └─ {% else %}
            └─ Display offline error + auto-refresh meta tag
               (<meta http-equiv="refresh" content="5">)

Response: HTML
│
└─→ Browser
   ├─ If online: Display sensor table
   └─ If offline: Display error + auto-refresh in 5 seconds
```

---

## Request/Response Schemas

### GET /api/sensors

**Request**:
```
GET /api/sensors?type=temperature HTTP/1.1
Host: localhost:8000
```

**Query Parameters**:
| Name | Type | Required | Default | Valid Values |
|------|------|----------|---------|--------------|
| type | str  | No       | None    | temperature, voltage, fan, current, power, clock, usage |

**Success Response (200 OK)**:
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
  {
    "id": 2,
    "sensor_index": 1,
    "type": "temperature",
    "name": "GPU Package",
    "unit": "°C",
    "value": 58.2,
    "value_min": 25.0,
    "value_max": 80.0,
    "value_avg": 55.0
  }
]
```

**Error Response (400 Bad Request)**:
```json
{
  "error": "Unknown type 'invalid'",
  "valid_types": ["clock", "current", "fan", "power", "temperature", "usage", "voltage"]
}
```

**Error Response (503 Service Unavailable)**:
```json
{
  "error": "HWInfo64 is not running or shared memory is unavailable"
}
```

---

### GET /health

**Request**:
```
GET /health HTTP/1.1
Host: localhost:8000
```

**Success Response (200 OK)**:
```json
{
  "status": "ok",
  "sensor_count": 42
}
```

**Error Response (503 Service Unavailable)**:
```json
{
  "status": "hwinfo_offline"
}
```

---

### GET /

**Request**:
```
GET / HTTP/1.1
Host: localhost:8000
```

**Success Response (200 OK)**:
```html
<!DOCTYPE html>
<html>
<head>
  <title>HWInfo API</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <!-- Auto-refresh if offline: <meta http-equiv="refresh" content="5"> -->
</head>
<body>
  <h1>HWInfo Sensor API</h1>
  <span class="badge online">● Online</span>

  <div class="section">
    <div class="section-title">temperature</div>
    <table>
      <thead>
        <tr>
          <th>Sensor</th>
          <th>Now</th><th>Min</th><th>Max</th><th>Avg</th><th>Unit</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>CPU Package</td>
          <td>65.50</td>
          <td>30.20</td>
          <td>85.10</td>
          <td>62.30</td>
          <td>°C</td>
        </tr>
        <!-- More rows -->
      </tbody>
    </table>
  </div>

  <!-- More sections for other types -->
</body>
</html>
```

**Error Response (200 OK with offline HTML)**:
```html
<!DOCTYPE html>
<html>
<head>
  <title>HWInfo API — Offline</title>
  <meta http-equiv="refresh" content="5">
</head>
<body>
  <h1>HWInfo Sensor API</h1>
  <span class="badge offline">● Offline</span>

  <div class="err">
    <div class="err-title">HWInfo64 is not running</div>
    <p>Start HWInfo64 and enable Settings → General → Shared Memory Support</p>
    <p>Auto-refreshing every 5 seconds…</p>
  </div>
</body>
</html>
```

---

## Deployment Topology

### Single Machine (Local Development)

```
Desktop / Laptop
└─ Browser (127.0.0.1:8000)
   └─ Uvicorn (main.py) on port 8000
      └─ HWInfo64 (running, shared memory enabled)
```

**Access**: `http://localhost:8000`

### LAN Deployment (Typical)

```
┌─────────────────────────────────────────┐
│ Server (Windows 10/11)                  │
│ ┌──────────────────────────────────┐    │
│ │ HWInfoAPI Windows Service        │    │
│ │ └─ .venv\Scripts\python main.py  │    │
│ │    ├─ Listens on 127.0.0.1:8000  │    │
│ │    └─ HWInfo64 integration        │    │
│ └──────────────┬───────────────────┘    │
│                │                        │
│ ┌──────────────▼───────────────────┐    │
│ │ Nginx Reverse Proxy              │    │
│ │ ├─ Listens on 0.0.0.0:80         │    │
│ │ └─ Forwards to 127.0.0.1:8000    │    │
│ └──────────────┬───────────────────┘    │
│                │                        │
│ Port 80 (HTTP) ┌────────────────────    │
│                │                        │
└────────────────┼────────────────────────┘
                 │ LAN (internal network)
    ┌────────────▼────────────┐
    │ Other Machines          │
    │ ├─ Browser              │
    │ ├─ IoT Device           │
    │ └─ Monitoring Tool      │
    │                         │
    └─ http://server.local/  │
       or http://192.168.x.x  │
```

**Access**: `http://hwinfo.local` (or `http://<server-ip>`)

### External Access (Not Recommended for Security)

```
Internet
  │
  └─ HTTPS Reverse Proxy
     (CloudFlare, AWS, etc.)
     │
     └─ VPN / Firewall
        │
        └─ LAN Server
           └─ HWInfoAPI
```

**Requirements** (if exposed):
- HTTPS only (SSL/TLS)
- API key authentication
- Rate limiting
- VPN or firewall access control

---

## Configuration Management

### Environment Variables (.env)

```
# File: .env (git-ignored, auto-loaded)
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info
```

**Precedence**:
1. `.env` file (if present)
2. Environment variables (if set)
3. Defaults (HOST=0.0.0.0, PORT=8000, LOG_LEVEL=info)

**Load Method**: Pydantic Settings (`config.py`)

### Service Configuration (NSSM)

**Settings Stored in Windows Registry** (`HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\HWInfoAPI`)

Key settings:
- `ImagePath`: `.venv\Scripts\python.exe`
- `AppPath`: `main.py` (arguments)
- `AppDirectory`: Service working directory
- `AppStdout`: Log file for stdout
- `AppStderr`: Log file for stderr
- `Start`: SERVICE_AUTO_START (3) or SERVICE_DEMAND_START (2)

**Modify**:
```powershell
nssm edit HWInfoAPI      # GUI editor
nssm get HWInfoAPI <key> # Read value
nssm set HWInfoAPI <key> <value>  # Set value
```

---

## Error Handling & Recovery

### Error Flow: HWInfo Offline

```
read_sensors()
├─ _read_raw()
│  └─ OpenFileMappingA(...) returns NULL
│     └─ Return None (not exception)
│
├─ Check: data is None? → Yes
│  └─ Return None
│
├─ api/routes.py checks:
│  ├─ sensors is None? → Return 503
│  └─ Dashboard shows offline page + auto-refresh
```

**Recovery**: Auto (once HWInfo restarts and enables shared memory, next request succeeds)

### Error Flow: Invalid Type Filter

```
get_sensors(sensor_type="invalid")
├─ Call read_sensors() → list[SensorReading]
├─ Validate: "invalid".lower() in _VALID_TYPES? → No
└─ Return 400 {"error": "Unknown type 'invalid'", "valid_types": [...]}
```

**Client Handling**: Show error message; retry with valid type

### Error Flow: Corrupted Shared Memory

```
parse_buffer(data)
├─ Unpack header
├─ Validate magic: header[0:4] == 0x57694853? → No
└─ _read_raw() returns None
   └─ read_sensors() returns None
      └─ All endpoints return 503
```

**Recovery**: Restart HWInfo64

---

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Open shared memory | <0.1ms | Windows kernel call |
| Copy buffer (50 sensors) | 0.1ms | ctypes.c_char array copy |
| struct.unpack (header) | <0.01ms | Binary parsing |
| Unpack entries (50 sensors) | 0.2ms | 50 × struct.unpack |
| Pydantic validation (50) | 0.5ms | Type checking + creation |
| Template render (50 sensors) | 2-5ms | Jinja2 table generation |
| **Total request**: | 3-10ms | Typical end-to-end |
| Memory per sensor | 200-300 bytes | SensorReading object |

**Scaling**: Linear with sensor count. 1000 sensors: ~20ms request time.

---

## Security Architecture

### Current (LAN-Only)

**Threat Model**: Trusted network, no authentication needed

**Controls**:
- Listens on 127.0.0.1 (loopback) or 0.0.0.0 (with reverse proxy)
- No credentials in requests
- No sensitive data in responses (only sensor values)
- Input validation (type filter against whitelist)

### Hardened (External Exposure)

**Additional Controls**:
- HTTPS only (TLS 1.2+)
- API key auth (`Authorization: Bearer <key>`)
- Rate limiting (e.g., 100 req/min per IP)
- Request logging (audit trail)
- CORS restrictions
- IP allowlist

**Example FastAPI auth middleware**:
```python
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

@router.get("/api/sensors")
def get_sensors(api_key: str = Depends(api_key_header)):
    if api_key != settings.api_key:
        raise HTTPException(status_code=403)
    # ...
```

---

## Monitoring & Observability

### Health Check Endpoint

```bash
curl http://localhost:8000/health
→ {"status": "ok", "sensor_count": 42}
```

**Usage**: Monitoring tools (Nagios, Zabbix, Prometheus) can poll `/health` periodically

### Logging

**Uvicorn Logs** (stdout):
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
INFO:     127.0.0.1:34567 - "GET /api/sensors HTTP/1.1" 200
INFO:     127.0.0.1:34568 - "GET /health HTTP/1.1" 200
```

**Service Logs** (NSSM):
- `./logs/stdout.log` — Uvicorn output
- `./logs/stderr.log` — Exceptions and errors

**Log Aggregation**: Forward logs to ELK, Splunk, or cloudwatch for centralized monitoring

---

## Extensibility & Future Enhancements

### Planned Features

1. **Polling/Background Updates**
   - Cache sensors in memory
   - Update every 1s via background task
   - Reduce per-request latency

2. **Webhooks**
   - Trigger alerts on threshold breaches (e.g., CPU > 90°C)
   - POST to external URLs

3. **Data Persistence**
   - SQLite/PostgreSQL logging
   - Historical analytics
   - Query past data

4. **Advanced Filtering**
   - Range queries: `?value_min=50&value_max=80`
   - ID-based queries: `?id=1,2,3`
   - Aggregations: `?aggregate=avg`

5. **WebSocket Real-Time**
   - Live streaming via WebSocket
   - Lower latency than HTTP polling

6. **Multi-Instance**
   - Query multiple servers
   - Aggregate sensors across machines

### Extension Points

- **New routes**: Add to `api/routes.py` and register with `app.include_router()`
- **New sensor types**: Update `SENSOR_TYPE_NAMES` in `hwinfo/models.py`
- **Custom filtering**: Add logic to `get_sensors()` in `api/routes.py`
- **Persistence**: Replace `read_sensors()` call with cached version

---

## Troubleshooting Flowchart

```
GET /health returns 503?
│
├─ Yes: HWInfo offline
│  │
│  └─ Start HWInfo64 → Check Settings → General → Shared Memory Support
│
└─ No: Service running
   │
   └─ GET /api/sensors returns 400?
      │
      ├─ Yes: Invalid type filter
      │  └─ Use valid type: temperature, voltage, fan, current, power, clock, usage
      │
      └─ No: Working correctly
         └─ Monitor logs: ./logs/stdout.log, ./logs/stderr.log
```

---

**Architecture Version**: 1.0  
**Last Updated**: May 2026  
**Python Version**: 3.13+
