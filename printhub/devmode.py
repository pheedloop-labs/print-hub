"""Capture and replay a printer's full DEVMODE, driver-private bytes included.

Vendor settings live in the dmDriverExtra bytes after the public DEVMODE.
No portable API reaches them and pywin32 hands you a DEVMODE object rather
than raw bytes, so this is a small ctypes layer over DocumentProperties and
SetPrinter.

Capture is the useful half. `apply` writes the queue default, which the ZC10L
re-asserts within ten seconds (CLAUDE.MD Verified 19) — delivery is per job,
via render.py's --devmode, not through the queue. Keep apply for capture-side
experiments and restores.

    python -m printhub.devmode show    <queue>
    python -m printhub.devmode capture <queue> <file>
    python -m printhub.devmode apply   <queue> <file>
    python -m printhub.devmode diff    <file-a> <file-b>

apply changes the queue for every user and needs manage-printer rights.
Capture a restore point before you ever call it.
"""

import ctypes
import ctypes.wintypes as wt
import hashlib
import sys

winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)

DM_OUT_BUFFER = 2
DM_IN_BUFFER = 8
PRINTER_ACCESS_ADMINISTER = 0x4
PRINTER_ACCESS_USE = 0x8
STANDARD_RIGHTS_REQUIRED = 0x000F0000
PRINTER_ALL_ACCESS = (STANDARD_RIGHTS_REQUIRED
                      | PRINTER_ACCESS_ADMINISTER
                      | PRINTER_ACCESS_USE)

# DEVMODEW public field offsets. dmDeviceName is 32 wide chars, so the
# numeric fields start at 64.
OFF_DEVICENAME = 0
OFF_SPECVERSION, OFF_DRIVERVERSION = 64, 66
OFF_SIZE, OFF_DRIVEREXTRA = 68, 70
OFF_FIELDS = 72
OFF_ORIENTATION, OFF_PAPERSIZE = 76, 78
OFF_PAPERLENGTH, OFF_PAPERWIDTH = 80, 82
OFF_SCALE, OFF_COPIES = 84, 86
OFF_DEFAULTSOURCE, OFF_PRINTQUALITY = 88, 90
OFF_COLOR, OFF_DUPLEX, OFF_YRESOLUTION = 92, 94, 96
OFF_TTOPTION, OFF_COLLATE = 98, 100
OFF_FORMNAME = 102
OFF_MEDIATYPE = 196


class PRINTER_DEFAULTS(ctypes.Structure):
    _fields_ = [("pDatatype", wt.LPWSTR),
                ("pDevMode", ctypes.c_void_p),
                ("DesiredAccess", wt.DWORD)]


class PRINTER_INFO_2W(ctypes.Structure):
    _fields_ = [
        ("pServerName", wt.LPWSTR), ("pPrinterName", wt.LPWSTR),
        ("pShareName", wt.LPWSTR), ("pPortName", wt.LPWSTR),
        ("pDriverName", wt.LPWSTR), ("pComment", wt.LPWSTR),
        ("pLocation", wt.LPWSTR), ("pDevMode", ctypes.c_void_p),
        ("pSepFile", wt.LPWSTR), ("pPrintProcessor", wt.LPWSTR),
        ("pDatatype", wt.LPWSTR), ("pParameters", wt.LPWSTR),
        ("pSecurityDescriptor", ctypes.c_void_p),
        ("Attributes", wt.DWORD), ("Priority", wt.DWORD),
        ("DefaultPriority", wt.DWORD), ("StartTime", wt.DWORD),
        ("UntilTime", wt.DWORD), ("Status", wt.DWORD),
        ("cJobs", wt.DWORD), ("AveragePPM", wt.DWORD),
    ]


winspool.OpenPrinterW.argtypes = [wt.LPCWSTR, ctypes.POINTER(wt.HANDLE),
                                  ctypes.POINTER(PRINTER_DEFAULTS)]
winspool.ClosePrinter.argtypes = [wt.HANDLE]
winspool.DocumentPropertiesW.restype = ctypes.c_long
winspool.DocumentPropertiesW.argtypes = [wt.HWND, wt.HANDLE, wt.LPCWSTR,
                                         ctypes.c_void_p, ctypes.c_void_p,
                                         wt.DWORD]
winspool.GetPrinterW.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p,
                                 wt.DWORD, ctypes.POINTER(wt.DWORD)]
winspool.SetPrinterW.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p,
                                 wt.DWORD]


def open_printer(queue, admin=False):
    handle = wt.HANDLE()
    defaults = PRINTER_DEFAULTS(
        None, None, PRINTER_ALL_ACCESS if admin else PRINTER_ACCESS_USE)
    if not winspool.OpenPrinterW(queue, ctypes.byref(handle),
                                 ctypes.byref(defaults)):
        raise OSError(f"OpenPrinter({queue!r}, admin={admin}) failed: "
                      f"WinError {ctypes.get_last_error()}")
    return handle


def capture(queue):
    """Return the queue's full default DEVMODE as raw bytes."""
    handle = open_printer(queue)
    try:
        needed = winspool.DocumentPropertiesW(None, handle, queue,
                                              None, None, 0)
        if needed <= 0:
            raise OSError(f"DocumentProperties size query returned {needed}")
        buf = ctypes.create_string_buffer(needed)
        rc = winspool.DocumentPropertiesW(None, handle, queue, buf, None,
                                          DM_OUT_BUFFER)
        if rc < 0:
            raise OSError(f"DocumentProperties(DM_OUT_BUFFER) returned {rc}")
        return buf.raw[:needed]
    finally:
        winspool.ClosePrinter(handle)


def _u16(blob, off):
    return int.from_bytes(blob[off:off + 2], "little")


def _i16(blob, off):
    return int.from_bytes(blob[off:off + 2], "little", signed=True)


def _u32(blob, off):
    return int.from_bytes(blob[off:off + 4], "little")


def _wstr(blob, off, chars):
    raw = blob[off:off + chars * 2].decode("utf-16-le", errors="replace")
    return raw.split("\x00", 1)[0]


def describe(blob):
    """Pull the public fields out of a DEVMODE blob."""
    size = _u16(blob, OFF_SIZE)
    extra = _u16(blob, OFF_DRIVEREXTRA)
    return {
        "device": _wstr(blob, OFF_DEVICENAME, 32),
        "form": _wstr(blob, OFF_FORMNAME, 32),
        "spec_version": _u16(blob, OFF_SPECVERSION),
        "driver_version": _u16(blob, OFF_DRIVERVERSION),
        "dmSize": size,
        "dmDriverExtra": extra,
        "total": size + extra,
        "blob_len": len(blob),
        "fields": _u32(blob, OFF_FIELDS),
        "orientation": _i16(blob, OFF_ORIENTATION),
        "paper_size": _i16(blob, OFF_PAPERSIZE),
        "paper_length": _i16(blob, OFF_PAPERLENGTH),
        "paper_width": _i16(blob, OFF_PAPERWIDTH),
        "scale": _i16(blob, OFF_SCALE),
        "copies": _i16(blob, OFF_COPIES),
        "default_source": _i16(blob, OFF_DEFAULTSOURCE),
        "print_quality": _i16(blob, OFF_PRINTQUALITY),
        "color": _i16(blob, OFF_COLOR),
        "duplex": _i16(blob, OFF_DUPLEX),
        "y_resolution": _i16(blob, OFF_YRESOLUTION),
        "collate": _i16(blob, OFF_COLLATE),
        "media_type": _u32(blob, OFF_MEDIATYPE),
        "public_sha256": hashlib.sha256(blob[:size]).hexdigest(),
        "private_sha256": hashlib.sha256(blob[size:size + extra]).hexdigest(),
        "whole_sha256": hashlib.sha256(blob).hexdigest(),
    }


def print_description(blob, label=""):
    d = describe(blob)
    if label:
        print(label)
    print(f"  device          : {d['device']!r}")
    print(f"  form            : {d['form']!r}")
    print(f"  dmSize          : {d['dmSize']}")
    print(f"  dmDriverExtra   : {d['dmDriverExtra']}  <- the vendor bytes")
    print(f"  total / blob    : {d['total']} / {d['blob_len']}")
    print(f"  spec/drv version: {d['spec_version']} / {d['driver_version']}")
    print(f"  dmFields        : 0x{d['fields']:08x}")
    print(f"  orientation     : {d['orientation']} (1=portrait 2=landscape)")
    print(f"  paper size id   : {d['paper_size']}")
    print(f"  paper w x l     : {d['paper_width']/10.0} x "
          f"{d['paper_length']/10.0} mm")
    print(f"  scale / copies  : {d['scale']} / {d['copies']}")
    print(f"  source / quality: {d['default_source']} / {d['print_quality']}")
    print(f"  color / duplex  : {d['color']} / {d['duplex']}")
    print(f"  yres / collate  : {d['y_resolution']} / {d['collate']}")
    print(f"  media type      : {d['media_type']}")
    print(f"  sha256 public   : {d['public_sha256'][:32]}")
    print(f"  sha256 private  : {d['private_sha256'][:32]}")
    print(f"  sha256 whole    : {d['whole_sha256'][:32]}")


def apply(queue, blob):
    """Write blob into the queue's default settings. Affects every user."""
    size = _u16(blob, OFF_SIZE)
    extra = _u16(blob, OFF_DRIVEREXTRA)
    if size + extra != len(blob):
        raise ValueError(f"blob is {len(blob)} bytes but declares "
                         f"dmSize {size} + dmDriverExtra {extra} = "
                         f"{size + extra}. Refusing to apply.")

    device = _wstr(blob, OFF_DEVICENAME, 32)
    if device.lower() != queue.lower():
        raise ValueError(f"blob was captured from {device!r}, not {queue!r}. "
                         f"Driver-private bytes are not portable between "
                         f"queues. Refusing to apply.")

    devmode = ctypes.create_string_buffer(blob, len(blob))

    handle = open_printer(queue, admin=True)
    try:
        needed = wt.DWORD()
        winspool.GetPrinterW(handle, 2, None, 0, ctypes.byref(needed))
        info_buf = ctypes.create_string_buffer(needed.value)
        if not winspool.GetPrinterW(handle, 2, info_buf, needed.value,
                                    ctypes.byref(needed)):
            raise OSError(f"GetPrinter level 2 failed: "
                          f"WinError {ctypes.get_last_error()}")

        info = ctypes.cast(info_buf, ctypes.POINTER(PRINTER_INFO_2W)).contents
        info.pDevMode = ctypes.cast(devmode, ctypes.c_void_p)
        # Never carry a security descriptor through a settings write.
        info.pSecurityDescriptor = None

        if not winspool.SetPrinterW(handle, 2, info_buf, 0):
            raise OSError(f"SetPrinter level 2 failed: "
                          f"WinError {ctypes.get_last_error()}. "
                          f"This needs manage-printer rights.")
    finally:
        winspool.ClosePrinter(handle)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]

    if cmd == "show" and len(sys.argv) == 3:
        print_description(capture(sys.argv[2]), f"queue {sys.argv[2]!r}")

    elif cmd == "capture" and len(sys.argv) == 4:
        queue, dest = sys.argv[2], sys.argv[3]
        blob = capture(queue)
        with open(dest, "wb") as f:
            f.write(blob)
        print(f"captured {len(blob)} bytes from {queue!r} -> {dest}")
        print_description(blob)

    elif cmd == "apply" and len(sys.argv) == 4:
        queue, src = sys.argv[2], sys.argv[3]
        with open(src, "rb") as f:
            blob = f.read()
        before = capture(queue)
        apply(queue, blob)
        after = capture(queue)
        print(f"applied {len(blob)} bytes to {queue!r}")
        print(f"  before : {hashlib.sha256(before).hexdigest()[:32]}")
        print(f"  wanted : {hashlib.sha256(blob).hexdigest()[:32]}")
        print(f"  after  : {hashlib.sha256(after).hexdigest()[:32]}")
        if after == blob:
            print("  => queue default now matches the blob exactly")
        else:
            print("  => MISMATCH. The driver rewrote or rejected part of it.")
            print("     Compare with: devmode diff <wanted> <after-file>")

    elif cmd == "diff" and len(sys.argv) == 4:
        with open(sys.argv[2], "rb") as f:
            a = f.read()
        with open(sys.argv[3], "rb") as f:
            b = f.read()
        print(f"a: {sys.argv[2]}  {len(a)} bytes")
        print(f"b: {sys.argv[3]}  {len(b)} bytes")
        if a == b:
            print("identical")
            return
        size = _u16(a, OFF_SIZE)
        pub_a, pub_b = a[:size], b[:size]
        print(f"public  section {'same' if pub_a == pub_b else 'DIFFERS'}")
        print(f"private section "
              f"{'same' if a[size:] == b[size:] else 'DIFFERS'}")
        n = min(len(a), len(b))
        offsets = [i for i in range(n) if a[i] != b[i]]
        print(f"{len(offsets)} differing bytes"
              f"{' (plus a length change)' if len(a) != len(b) else ''}")
        for i in offsets[:40]:
            where = "public" if i < size else f"private+{i - size}"
            print(f"  offset {i:<6} {where:<14} {a[i]:#04x} -> {b[i]:#04x}")
        if len(offsets) > 40:
            print(f"  ... {len(offsets) - 40} more")

    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
