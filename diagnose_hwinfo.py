"""
HWInfo64 shared memory diagnostic — run this directly to see exactly where access fails.
Usage: python diagnose_hwinfo.py
"""

import ctypes
import struct
import sys

if sys.platform != "win32":
    print("ERROR: This tool only works on Windows.")
    sys.exit(1)

SM_NAME = "Global\\HWiNFO_SENS_SM2"
SM_NAME_ALT = "HWiNFO_SENS_SM2"  # without Global\ prefix
MAGIC = 0x53695748  # "HWiS" as little-endian uint32
FILE_MAP_READ = 0x0004
HEADER_FMT = "<IIIqIIIIII"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

k32 = ctypes.windll.kernel32
k32.OpenFileMappingA.restype = ctypes.c_void_p
k32.MapViewOfFile.restype = ctypes.c_void_p
k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
k32.CloseHandle.argtypes = [ctypes.c_void_p]
k32.GetLastError.restype = ctypes.c_ulong

def try_open(name: str) -> None:
    print(f"\n--- Trying: {name!r} ---")
    handle = k32.OpenFileMappingA(FILE_MAP_READ, False, name.encode("ascii"))
    err = k32.GetLastError()
    if not handle:
        print(f"  OpenFileMappingA FAILED — handle=0  LastError={err}")
        if err == 2:
            print("  → ERROR_FILE_NOT_FOUND: Shared memory does not exist.")
            print("    Possible causes:")
            print("    1. HWInfo64 shared memory support not enabled (Settings > Shared Memory Support)")
            print("    2. HWInfo64 is not running")
            print("    3. You need to click 'Start' (sensors window) in HWInfo64, not just open it")
        elif err == 5:
            print("  → ERROR_ACCESS_DENIED: Object exists but access denied.")
            print("    Fix: Run this script (and the API server) as Administrator.")
        else:
            print(f"  → Unknown error code {err}")
        return

    print(f"  OpenFileMappingA OK — handle={handle:#x}  LastError={err}")

    ptr = k32.MapViewOfFile(handle, FILE_MAP_READ, 0, 0, 0)
    err2 = k32.GetLastError()
    if not ptr:
        print(f"  MapViewOfFile FAILED — ptr=0  LastError={err2}")
        k32.CloseHandle(handle)
        return

    print(f"  MapViewOfFile OK — ptr={ptr:#x}")

    try:
        header_bytes = bytes((ctypes.c_char * HEADER_SIZE).from_address(ptr))
        magic = struct.unpack_from("<I", header_bytes)[0]
        print(f"  Magic bytes: {magic:#010x}  (expected {MAGIC:#010x})")
        if magic != MAGIC:
            print("  MAGIC MISMATCH — shared memory exists but header is wrong.")
            print("  This might mean a different program is using the same name.")
            return

        vals = struct.unpack(HEADER_FMT, header_bytes)
        ver, ver2 = vals[1], vals[2]
        sensor_cnt = vals[6]
        entry_off, entry_sz, entry_cnt = vals[7], vals[8], vals[9]
        print(f"  Header OK: version={ver}.{ver2}  sensors={sensor_cnt}  entries={entry_cnt}")
        print(f"  Entry layout: offset={entry_off}  size={entry_sz}  count={entry_cnt}")
        print(f"\n  SUCCESS: HWInfo64 shared memory is accessible with {entry_cnt} sensor entries.")

    finally:
        k32.UnmapViewOfFile(ptr)
        k32.CloseHandle(handle)


print("=" * 60)
print("HWInfo64 Shared Memory Diagnostic")
print("=" * 60)

# Check if running as admin
is_admin = ctypes.windll.shell32.IsUserAnAdmin()
print(f"\nRunning as Administrator: {'YES' if is_admin else 'NO'}")

try_open(SM_NAME)
try_open(SM_NAME_ALT)

print("\n" + "=" * 60)
