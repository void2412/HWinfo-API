"""
Read HWInfo64 sensor data from Windows named shared memory (Global\\HWiNFO_SENS_SM2).
On-demand: each call opens, reads, and closes the mapping - no persistent handles.
Returns None when HWInfo is not running (shared memory absent).
"""

import struct
import sys
from typing import Optional

from hwinfo.models import SensorReading, SENSOR_TYPE_NAMES

HWINFO_SM_NAME = "Global\\HWiNFO_SENS_SM2"
HWINFO_MAGIC = 0x53695748  # "HWiS" as little-endian uint32 (bytes: 48 57 69 53)

# Header layout (packed, no alignment padding):
#   magic(u32), ver(u32), ver2(u32), last_update(i64),
#   sensor_off(u32), sensor_sz(u32), sensor_cnt(u32),
#   entry_off(u32), entry_sz(u32), entry_cnt(u32)  → 44 bytes
_HEADER_FMT = "<IIIqIIIIII"
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)  # 44

# Entry layout (meaningful portion, 316 bytes; real size read from header ~320):
#   type(u32), sensor_idx(u32), id(u32),
#   name_orig[128], name_user[128], unit[16],
#   value(f64), value_min(f64), value_max(f64), value_avg(f64)
_ENTRY_FMT = "<III128s128s16sdddd"
_ENTRY_MEANINGFUL = struct.calcsize(_ENTRY_FMT)  # 316

# Hardware sensor (parent device) layout: id(u32), instance(u32), name_orig[128], name_user[128]
_SENSOR_FMT = "<II128s128s"
_SENSOR_MEANINGFUL = struct.calcsize(_SENSOR_FMT)  # 264


if sys.platform == "win32":
    import ctypes

    _k32 = ctypes.windll.kernel32
    _FILE_MAP_READ = 0x0004
    # Correct return types for 64-bit pointer safety
    _k32.OpenFileMappingA.restype = ctypes.c_void_p
    _k32.MapViewOfFile.restype = ctypes.c_void_p
    _k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    _k32.CloseHandle.argtypes = [ctypes.c_void_p]

    def _read_raw() -> Optional[bytes]:
        """Open HWInfo shared memory, copy contents, close. Returns None if unavailable."""
        handle = _k32.OpenFileMappingA(
            _FILE_MAP_READ, False, HWINFO_SM_NAME.encode("ascii")
        )
        if not handle:
            return None

        ptr = _k32.MapViewOfFile(handle, _FILE_MAP_READ, 0, 0, 0)
        if not ptr:
            _k32.CloseHandle(handle)
            return None

        try:
            header_bytes = bytes((ctypes.c_char * _HEADER_SIZE).from_address(ptr))
            if struct.unpack_from("<I", header_bytes)[0] != HWINFO_MAGIC:
                return None

            vals = struct.unpack(_HEADER_FMT, header_bytes)
            sensor_off, sensor_size, sensor_count = vals[4], vals[5], vals[6]
            entry_off, entry_size, entry_count = vals[7], vals[8], vals[9]
            total = max(
                sensor_off + sensor_size * sensor_count,
                entry_off + entry_size * entry_count,
            )
            # Guard against corrupted/spoofed shared memory with bogus sizes
            if total > 64 * 1024 * 1024 or total < _HEADER_SIZE:
                return None
            return bytes((ctypes.c_char * total).from_address(ptr))
        finally:
            _k32.UnmapViewOfFile(ptr)
            _k32.CloseHandle(handle)

else:
    def _read_raw() -> Optional[bytes]:
        raise OSError("HWInfo64 shared memory is only available on Windows")


def _parse_hardware_names(data: bytes) -> dict[int, str]:
    """Build a map of sensor_index → hardware device name from the sensors section."""
    vals = struct.unpack_from(_HEADER_FMT, data)
    sensor_off, sensor_size, sensor_count = vals[4], vals[5], vals[6]

    names: dict[int, str] = {}
    for i in range(sensor_count):
        offset = sensor_off + i * sensor_size
        chunk = data[offset : offset + _SENSOR_MEANINGFUL]
        if len(chunk) < _SENSOR_MEANINGFUL:
            break
        _sid, _sinst, name_orig, name_user = struct.unpack(_SENSOR_FMT, chunk)
        names[i] = (
            name_user.rstrip(b"\x00") or name_orig.rstrip(b"\x00")
        ).decode("utf-8", errors="replace")

    return names


def parse_buffer(data: bytes) -> list[SensorReading]:
    """Parse raw shared memory bytes into sensor readings. Pure — no IO, fully testable."""
    vals = struct.unpack_from(_HEADER_FMT, data)
    entry_off, entry_size, entry_count = vals[7], vals[8], vals[9]

    hw_names = _parse_hardware_names(data)

    readings: list[SensorReading] = []
    for i in range(entry_count):
        offset = entry_off + i * entry_size
        chunk = data[offset : offset + _ENTRY_MEANINGFUL]
        if len(chunk) < _ENTRY_MEANINGFUL:
            break

        s_type, s_idx, s_id, name_orig, name_user, unit, val, vmin, vmax, vavg = (
            struct.unpack(_ENTRY_FMT, chunk)
        )

        # Prefer user-customized name; fall back to original hardware name
        entry_name = (
            name_user.rstrip(b"\x00") or name_orig.rstrip(b"\x00")
        ).decode("utf-8", errors="replace")

        # Prefix with hardware device name (e.g., "AMD Radeon RX 9070 XT: GPU Temperature")
        hw_name = hw_names.get(s_idx, "")
        name = f"{hw_name}: {entry_name}" if hw_name else entry_name

        readings.append(
            SensorReading(
                id=s_id,
                sensor_index=s_idx,
                type=SENSOR_TYPE_NAMES.get(s_type, "other"),
                name=name,
                unit=unit.rstrip(b"\x00").decode("utf-8", errors="replace"),
                value=val,
                value_min=vmin,
                value_max=vmax,
                value_avg=vavg,
            )
        )

    return readings


def read_sensors() -> Optional[list[SensorReading]]:
    """Read all sensors from HWInfo64. Returns None when HWInfo is not running."""
    data = _read_raw()
    if data is None:
        return None
    return parse_buffer(data)
