from pydantic import BaseModel

# Maps HWInfo sensor type integer to a human-readable string
SENSOR_TYPE_NAMES: dict[int, str] = {
    0: "none",
    1: "temperature",
    2: "voltage",
    3: "fan",
    4: "current",
    5: "power",
    6: "clock",
    7: "usage",
    8: "other",
}


class SensorReading(BaseModel):
    id: int
    sensor_index: int
    type: str
    name: str
    unit: str
    value: float
    value_min: float
    value_max: float
    value_avg: float
