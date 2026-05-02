# HWInfo64 Sensor API — Codebase Summary

Complete technical overview of the repository structure, module relationships, and design patterns.

## Project Overview

**HWInfo64 Sensor API** is a Python FastAPI service exposing hardware sensor data from Windows via REST and HTML endpoints. It reads from HWInfo64's named shared memory (`Global\HWiNFO_SENS_SM2`) on-demand without external dependencies, validating data with Pydantic v2, and serving both JSON APIs and a live web dashboard.

**Lines of Code**:
- Production code: ~250 LOC (main.py, config.py, hwinfo/*, api/*)
- Tests: ~300 LOC
- Templates: ~120 LOC (status.html)
- Total: ~670 LOC

**Key Principles**: Type safety, testability, minimal dependencies, Windows-native I/O (no libraries for shared memory)

---

## Directory Structure

```
HWinfo-API/
├── main.py                 # 40 LOC — FastAPI app initialization, "/" route
├── config.py               # 18 LOC — Pydantic Settings (environment config)
├── requirements.txt        # Dependencies
├── .env.example            # Config template
├── nssm.exe                # Windows service manager executable
│
├── hwinfo/                 # Hardware sensor reader
│   ├── __init__.py
│   ├── reader.py           # 120 LOC — Shared memory I/O, buffer parsing
│   └── models.py           # 27 LOC — Pydantic SensorReading, type mappings
│
├── api/                    # REST endpoints
│   ├── __init__.py
│   └── routes.py           # 41 LOC — GET /api/sensors, GET /health
│
├── templates/
│   └── status.html         # 120 LOC — Dashboard UI (Jinja2)
│
├── tests/                  # Pytest suite
│   ├── __init__.py
│   ├── test_reader.py      # 80+ LOC — parse_buffer() synthetic tests
│   └── test_routes.py      # 60+ LOC — FastAPI integration tests (mocked)
│
├── logs/                   # Runtime logs (created on first run/service start)
├── docs/                   # Documentation
└── .git/                   # Version control
```

---

## Module Breakdown

### main.py — Application Entry Point

**Purpose**: FastAPI app definition and "/" HTML dashboard route.

**Key Components**:
- `app = FastAPI(...)` — Initialize app with title/version metadata
- `templates = Jinja2Templates(...)` — Render status.html
- `@app.get("/")` — Dashboard handler; calls `read_sensors()`, groups by type, renders template

**Relationships**:
- Imports `config.settings` (host/port/log_level)
- Imports `hwinfo.reader.read_sensors()` (core sensor fetch)
- Imports `api.routes.router` (register /api/* endpoints)

**Design Decision**: Dashboard groups sensors by type server-side for cleaner template rendering. Returns `{"online": bool, "grouped": dict}` context to template.

---

### config.py — Configuration Management

**Purpose**: Load environment variables via Pydantic Settings.

**Key Components**:
- `Settings` — Pydantic BaseSettings with three fields:
  - `host: str = "0.0.0.0"` — Bind address (default accepts all interfaces for reverse proxy)
  - `port: int = 8000` — HTTP port
  - `log_level: str = "info"` — Uvicorn log level
- `settings = Settings()` — Singleton instance used throughout app

**Configuration Source**:
- Loads from `.env` file in project root (optional; falls back to defaults)
- File format: `KEY=value` (one per line)

**Relationships**:
- Used by `main.py` (host, port, log_level for uvicorn.run)

---

### hwinfo/models.py — Data Models

**Purpose**: Pydantic v2 models and sensor type constants.

**Key Components**:
- `SENSOR_TYPE_NAMES: dict[int, str]` — Maps HWInfo type codes to human names:
  - 0 → "none", 1 → "temperature", 2 → "voltage", 3 → "fan", 4 → "current", 5 → "power", 6 → "clock", 7 → "usage", 8 → "other"
- `SensorReading` — Pydantic BaseModel:
  - Fields: `id`, `sensor_index`, `type`, `name`, `unit`, `value`, `value_min`, `value_max`, `value_avg`
  - Auto validation (float fields, string fields, etc.)
  - `.model_dump()` for JSON serialization

**Relationships**:
- Used by `hwinfo/reader.py` (instantiate SensorReading from parsed buffer)
- Used by `api/routes.py` (type filtering)
- Returned by all API endpoints

**Design Decision**: Pydantic v2 `BaseModel` chosen for strict typing and auto JSON serialization; no custom serializers needed.

---

### hwinfo/reader.py — Shared Memory Reader (Core Logic)

**Purpose**: Read HWInfo64 sensor data from Windows named shared memory without external dependencies.

**Key Components**:

#### Constants & Format Strings
```python
HWINFO_SM_NAME = "Global\\HWiNFO_SENS_SM2"
HWINFO_MAGIC = 0x57694853  # "SiWH" magic number (validation)
_HEADER_FMT = "<IIIqIIIIII"  # Binary struct format for 44-byte header
_ENTRY_FMT = "<III128s128s16sdddd"  # Entry format (316 meaningful bytes)
```

#### Functions

**`_read_raw() -> Optional[bytes]`** (Windows-only, 25 LOC)
- Opens HWInfo shared memory mapping via `kernel32.OpenFileMappingA()`
- Maps view via `kernel32.MapViewOfFile()`
- Reads raw bytes (header + all entries)
- Validates magic number (0x57694853)
- Bounds-checks total size (max 64MB, min header size)
- Unmaps and closes handle; returns None if unavailable
- **ctypes.windll.kernel32** used directly; no mmap library needed

**`parse_buffer(data: bytes) -> list[SensorReading]`** (Pure function, 35 LOC)
- Unpacks 44-byte header: entry offset, entry size, entry count
- Loops over entries; unpacks 316-byte chunks into struct format
- Decodes string fields (name_orig, name_user, unit) as UTF-8 with fallback
- Prefers `name_user` if set; falls back to `name_orig`
- Maps type code via `SENSOR_TYPE_NAMES`
- Returns list of validated `SensorReading` objects
- **Fully testable**: takes bytes, returns structured data; no I/O

**`read_sensors() -> Optional[list[SensorReading]]`** (Public API, 6 LOC)
- Calls `_read_raw()` to fetch bytes
- Returns None if unavailable
- Parses buffer and returns sensor list

#### Error Handling
- Returns None (not exception) when HWInfo unavailable — allows graceful 503 responses
- Magic number validation prevents parsing corrupted/spoofed shared memory
- Size bounds check prevents integer overflow attacks
- UTF-8 decode with fallback prevents crashes on invalid text

**Relationships**:
- Imports `hwinfo.models` (SensorReading, SENSOR_TYPE_NAMES)
- Called by `main.py` (dashboard) and `api/routes.py` (JSON endpoints)

**Design Decision**: Platform-specific code isolated to `_read_raw()` with clear Windows/non-Windows branches. `parse_buffer()` is pure and unit-testable via synthetic buffers.

---

### api/routes.py — REST Endpoints

**Purpose**: FastAPI router with two endpoints.

**Key Components**:

**`GET /api/sensors`** (15 LOC)
- Query param `type` (optional) — filter by sensor type
- Returns 503 if HWInfo offline
- Validates type against `_VALID_TYPES` set (excludes "none")
- Filters sensors by type if provided; returns 400 with valid types list if invalid
- Returns list of sensor JSON objects

**`GET /health`** (6 LOC)
- Returns `{"status": "ok", "sensor_count": N}` if online
- Returns 503 with `{"status": "hwinfo_offline"}` if offline

**Relationships**:
- Imported by `main.py` as `router` and registered with `app.include_router(router)`
- Calls `hwinfo.reader.read_sensors()` (shared sensor fetch)
- Uses `hwinfo.models.SENSOR_TYPE_NAMES` (valid type set)

**Design Decision**: Both endpoints call `read_sensors()` independently (no caching) to always reflect current state. No authentication layer (assumes LAN-only access via nginx reverse proxy).

---

## Data Flow

### Request → Response Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Client (Browser / JSON API Consumer)                        │
└────────────────────┬────────────────────────────────────────┘
                     │
        HTTP Request (/, /api/sensors, /health)
                     │
        ┌────────────▼────────────┐
        │ main.py / api/routes.py │
        │ (FastAPI handlers)      │
        └────────────┬────────────┘
                     │
           Call read_sensors()
                     │
        ┌────────────▼────────────────────┐
        │ hwinfo/reader.read_sensors()    │
        │ ├─ _read_raw()                  │
        │ │  └─ Opens HWInfo shared mem   │
        │ └─ parse_buffer()               │
        │    └─ Struct unpacking          │
        └────────────┬────────────────────┘
                     │
      Returns list[SensorReading] | None
                     │
        ┌────────────▼────────────┐
        │ Pydantic Validation     │
        │ (auto on instantiation) │
        └────────────┬────────────┘
                     │
      ┌─────────────┴──────────────┐
      │                            │
   ┌──▼─────────────┐   ┌─────────▼──────────┐
   │ "/" route      │   │ "/api/sensors" etc │
   │ ├─ Group       │   │ ├─ model_dump()    │
   │ │  by type     │   │ │  (JSON serial)   │
   │ └─ Render      │   │ └─ Return JSON     │
   │    status.html │   │    + status code   │
   └──┬─────────────┘   └─────────┬──────────┘
      │                          │
      └─────────────┬────────────┘
                    │
            HTTP Response (HTML / JSON)
                    │
        ┌───────────▼────────────┐
        │ Client Browser / App   │
        │ Display / Parse        │
        └───────────────────────┘
```

### Sensor Reading Struct (Shared Memory)

HWInfo64 shared memory layout (per entry):

```
Offset  Type       Field              Size   Comment
──────  ────       ─────              ────   ───────
0       uint32     type               4      Sensor type code (0-8)
4       uint32     sensor_index       4      Index within sensor group
8       uint32     id                 4      Unique sensor ID
12      char[128]  name_orig          128    Hardware name (fixed)
140     char[128]  name_user          128    User-customized name
268     char[16]   unit               16     Unit string (°C, V, RPM, etc.)
284     double     value              8      Current reading
292     double     value_min          8      Min recorded
300     double     value_max          8      Max recorded
308     double     value_avg          8      Average recorded
─────────────────────────────────────────────────
Total Meaningful: 316 bytes
Actual Entry:     320 bytes (4 bytes padding/reserved)
```

**Header (44 bytes total)**:
- Offset 0: Magic (0x57694853 = "SiWH")
- Offset 4-8: Version fields
- Offset 12: Last update timestamp
- Offset 20-24: Sensor array metadata (offset, size, count)
- Offset 28-32: Entry array metadata (offset, size, count)

---

## Testing Strategy

### Test Files

**tests/test_reader.py** (~80 LOC)
- Synthetic shared memory buffers (no live HWInfo)
- Tests `parse_buffer()` with various sensor types, edge cases
- Tests name preference (user name > orig name)
- Tests invalid magic number rejection
- Tests entry iteration

**tests/test_routes.py** (~60 LOC)
- FastAPI TestClient integration
- Mocks `read_sensors()` with controlled return values
- Tests GET / (online/offline states)
- Tests GET /api/sensors (all sensors, type filtering, invalid type)
- Tests GET /health (online/offline)
- Tests HTTP status codes (200, 400, 503)

### Test Coverage
- **Sensor reading**: Pure function `parse_buffer()` fully testable
- **API routes**: Mocked reader, no live HWInfo dependency
- **Error cases**: Invalid types, offline state, malformed data

**Run tests**:
```bash
pytest
pytest --cov=hwinfo --cov=api
pytest -v  # Verbose
```

---

## Key Design Decisions

### 1. No External Libraries for Shared Memory
- **Rationale**: Minimize dependencies, avoid mmap; use ctypes (stdlib) for direct kernel32 calls
- **Tradeoff**: Platform-specific (Windows-only), but codebase stays tiny

### 2. Return None for Offline (Not Exception)
- **Rationale**: Expected behavior (HWInfo may not be running); allows clean 503 responses
- **Tradeoff**: Caller must check `is None` (but explicit is better than implicit)

### 3. Pure `parse_buffer()` Function
- **Rationale**: Fully testable without I/O, allows synthetic buffer tests
- **Tradeoff**: Separation of concerns (I/O in `_read_raw()`, parsing in `parse_buffer()`)

### 4. Pydantic v2 for Validation
- **Rationale**: Type safety, auto JSON serialization, clear field validation
- **Tradeoff**: Runtime validation cost (negligible for 50-100 sensors)

### 5. No Caching/Polling
- **Rationale**: On-demand read per request; fresh data always; no stale readings
- **Tradeoff**: Slight overhead per request (but HWInfo memory read is <1ms)

### 6. Fastapi + Uvicorn
- **Rationale**: Modern, fast, async-capable, minimal boilerplate
- **Tradeoff**: Python only (no static compilation), but suitable for LAN service

### 7. Server-Side Type Grouping
- **Rationale**: Cleaner template; single loop over grouped dict
- **Tradeoff**: Grouping logic in Python (could be client-side), but small cost

---

## Configuration & Deployment

### Environment Variables (.env)
```env
HOST=0.0.0.0              # Listen address (0.0.0.0 = all interfaces)
PORT=8000                 # HTTP port
LOG_LEVEL=info            # Uvicorn log level (debug, info, warning, error, critical)
```

**Defaults**: All optional; used if .env missing.

### Service Deployment (NSSM)
- **Service Name**: HWInfoAPI
- **Executable**: `.venv\Scripts\python.exe`
- **Arguments**: `main.py` (or full path)
- **Start Type**: AUTO_START (optional)
- **Logs**: Redirect to `./logs/` directory

See README.md for detailed NSSM setup.

---

## Dependencies

| Package              | Version | Use Case                      |
|----------------------|---------|-------------------------------|
| fastapi              | 0.115+  | REST framework                |
| uvicorn[standard]    | 0.30+   | ASGI server                   |
| pydantic-settings    | 2.0+    | Environment config            |
| jinja2               | 3.1+    | HTML templating               |
| pytest               | 8.0+    | Test runner (dev)             |
| httpx                | 0.27+   | Test client (dev)             |

**Stdlib Only for Production**: ctypes, struct, sys, pathlib, logging

---

## Extending the Project

### Adding a New Endpoint

1. Add function to `api/routes.py`:
   ```python
   @router.get("/api/stats")
   def get_stats():
       sensors = read_sensors()
       if sensors is None:
           return JSONResponse(status_code=503, content={"error": "offline"})
       # Calculate stats...
       return {...}
   ```

2. Add test to `tests/test_routes.py`:
   ```python
   def test_stats_online():
       with patch("api.routes.read_sensors", return_value=[...]):
           r = client.get("/api/stats")
       assert r.status_code == 200
       assert "stat_field" in r.json()
   ```

### Adding a Sensor Type

1. Update `hwinfo/models.py`:
   ```python
   SENSOR_TYPE_NAMES[9] = "my_new_type"
   ```

2. No other changes needed (filter logic auto-includes new type)

### Changing Update Frequency

- Current: On-demand (per request)
- To poll periodically: Add background task in `main.py` with `asyncio.create_task()`
- Would require caching (Redis/in-memory) to avoid race conditions

---

## Common Pitfalls & Solutions

| Issue                          | Symptom                    | Fix                                           |
|--------------------------------|----------------------------|-----------------------------------------------|
| HWInfo shared memory disabled  | 503 errors                 | Enable in HWInfo: Settings → General → Shared Memory |
| .env syntax error              | Config load fails          | Ensure `KEY=value` format, no quotes          |
| Port already in use            | `Address already in use`   | Change PORT in .env or kill process on port   |
| Parse buffer offset error      | Empty sensors or crash     | Update HWInfo64 to latest version             |
| Service won't start            | Service fails immediately  | Check logs in ./logs/; verify Python path     |
| Dashboard shows old data       | Stale readings             | Refresh browser (no caching)                  |

---

## Performance Notes

- **Sensor Read**: ~1ms (shared memory copy + struct unpack)
- **Template Render**: ~5ms (Jinja2 for 50 sensors)
- **Total Request**: ~10ms typical (depends on sensor count)
- **Memory**: ~50MB baseline + ~1MB per 100 sensors
- **CPU**: Negligible (on-demand, low frequency)

---

## Security Considerations

### Current State (LAN Only)
- No authentication (assumes trusted LAN)
- No HTTPS (nginx reverse proxy recommended for external access)
- No rate limiting (trusted clients)

### Production Hardening (If Exposed)
- Add API key auth (`Authorization: Bearer token`)
- Enable CORS / CSRF protection (FastAPI middleware)
- Rate limit (slowapi or custom middleware)
- Use HTTPS (nginx with cert)
- Add request logging (structured logs)

---

## Maintenance & Monitoring

### Health Checks
```bash
# Daemon health
curl http://localhost:8000/health

# Expected: {"status": "ok", "sensor_count": 42}
```

### Log Locations
- **Service stdout/stderr**: `./logs/stdout.log`, `./logs/stderr.log` (NSSM redirects)
- **Uvicorn logs**: Console output (if running manually)

### Upgrade Path
1. Stop service (or kill uvicorn)
2. Update code (git pull / copy new files)
3. Run tests (`pytest`)
4. Restart service

---

**Document Version**: 1.0  
**Last Updated**: May 2026  
**Python Version**: 3.13+
