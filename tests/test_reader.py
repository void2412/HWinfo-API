"""
Unit tests for hwinfo/reader.py parse_buffer().
Builds synthetic shared memory buffers — no live HWInfo required.
"""

import struct
import pytest

from hwinfo.reader import (
    parse_buffer,
    _HEADER_FMT,
    _HEADER_SIZE,
    _ENTRY_FMT,
    _ENTRY_MEANINGFUL,
    HWINFO_MAGIC,
)

_ENTRY_SIZE = 320  # real HWInfo entry size (316 meaningful + 4 reserved)


def _make_entry(
    type_: int = 1,
    sensor_index: int = 0,
    id_: int = 1,
    name_orig: str = "Test Sensor",
    name_user: str = "",
    unit: str = "C",
    value: float = 42.0,
    value_min: float = 40.0,
    value_max: float = 50.0,
    value_avg: float = 45.0,
) -> bytes:
    packed = struct.pack(
        _ENTRY_FMT,
        type_,
        sensor_index,
        id_,
        name_orig.encode("utf-8"),
        name_user.encode("utf-8"),
        unit.encode("utf-8"),
        value,
        value_min,
        value_max,
        value_avg,
    )
    return packed + b"\x00" * (_ENTRY_SIZE - _ENTRY_MEANINGFUL)


def _make_buffer(entries: list[bytes]) -> bytes:
    entry_off = _HEADER_SIZE  # entries start immediately after header
    header = struct.pack(
        _HEADER_FMT,
        HWINFO_MAGIC,          # magic
        2, 0, 0,               # version, version2, last_update
        entry_off, 0, 0,       # sensor_off, sensor_size, sensor_count (not used by reader)
        entry_off, _ENTRY_SIZE, len(entries),  # entry_off, entry_size, entry_count
    )
    return header + b"".join(entries)


# ── parse_buffer tests ─────────────────────────────────────────────────────────

def test_single_temperature_sensor():
    buf = _make_buffer([_make_entry(type_=1, name_orig="CPU Temp", unit="C", value=65.5)])
    sensors = parse_buffer(buf)
    assert len(sensors) == 1
    s = sensors[0]
    assert s.type == "temperature"
    assert s.name == "CPU Temp"
    assert s.unit == "C"
    assert s.value == 65.5


def test_name_user_takes_priority_over_name_orig():
    buf = _make_buffer([_make_entry(name_orig="CPU [#0]: Core 0", name_user="CPU Core 0")])
    sensors = parse_buffer(buf)
    assert sensors[0].name == "CPU Core 0"


def test_falls_back_to_name_orig_when_user_empty():
    buf = _make_buffer([_make_entry(name_orig="CPU Fan", name_user="")])
    sensors = parse_buffer(buf)
    assert sensors[0].name == "CPU Fan"


def test_empty_entry_list():
    sensors = parse_buffer(_make_buffer([]))
    assert sensors == []


def test_multiple_sensor_types():
    entries = [
        _make_entry(type_=1, name_orig="CPU Temp", unit="C",   value=70.0, id_=1),
        _make_entry(type_=3, name_orig="CPU Fan",  unit="RPM", value=1500.0, id_=2),
        _make_entry(type_=2, name_orig="Vcore",    unit="V",   value=1.35, id_=3),
    ]
    sensors = parse_buffer(_make_buffer(entries))
    assert len(sensors) == 3
    assert {s.type for s in sensors} == {"temperature", "fan", "voltage"}


def test_unknown_type_maps_to_other():
    buf = _make_buffer([_make_entry(type_=99)])
    sensors = parse_buffer(buf)
    assert sensors[0].type == "other"


def test_min_max_avg_values():
    buf = _make_buffer([
        _make_entry(value=50.0, value_min=30.0, value_max=80.0, value_avg=55.0)
    ])
    s = parse_buffer(buf)[0]
    assert s.value == 50.0
    assert s.value_min == 30.0
    assert s.value_max == 80.0
    assert s.value_avg == 55.0


def test_sensor_id_and_index_preserved():
    buf = _make_buffer([_make_entry(id_=42, sensor_index=7)])
    s = parse_buffer(buf)[0]
    assert s.id == 42
    assert s.sensor_index == 7


def test_all_sensor_type_names():
    type_map = {
        1: "temperature", 2: "voltage", 3: "fan", 4: "current",
        5: "power", 6: "clock", 7: "usage", 8: "other",
    }
    entries = [_make_entry(type_=t, id_=t) for t in type_map]
    sensors = parse_buffer(_make_buffer(entries))
    for s in sensors:
        assert s.type == type_map[s.id]
