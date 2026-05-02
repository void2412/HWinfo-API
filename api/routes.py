from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from hwinfo.reader import read_sensors
from hwinfo.models import SENSOR_TYPE_NAMES

router = APIRouter()

_VALID_TYPES = set(SENSOR_TYPE_NAMES.values()) - {"none"}


@router.get("/api/sensors")
def get_sensors(sensor_type: str | None = Query(default=None, alias="type")):
    """Return all sensor readings as JSON. Filter by sensor type with ?type=temperature"""
    sensors = read_sensors()
    if sensors is None:
        return JSONResponse(
            status_code=503,
            content={"error": "HWInfo64 is not running or shared memory is unavailable"},
        )

    if sensor_type is not None:
        t = sensor_type.lower()
        if t not in _VALID_TYPES:
            return JSONResponse(
                status_code=400,
                content={"error": f"Unknown type '{sensor_type}'", "valid_types": sorted(_VALID_TYPES)},
            )
        sensors = [s for s in sensors if s.type == t]

    return [s.model_dump() for s in sensors]


@router.get("/health")
def health():
    """Return HWInfo connection status and sensor count."""
    sensors = read_sensors()
    if sensors is None:
        return JSONResponse(status_code=503, content={"status": "hwinfo_offline"})
    return {"status": "ok", "sensor_count": len(sensors)}
