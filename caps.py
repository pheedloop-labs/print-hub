"""Dump a print queue's paper forms, paperkind ids, and DEVMODE defaults.

    C:\\hub\\.venv\\Scripts\\python.exe C:\\hub\\caps.py HUB-CARD

DC_PAPERSIZE reports each form in tenths of a millimetre, which is the unit
DEVMODE itself uses for dmPaperWidth / dmPaperLength. Everything here is read
only. It opens no dialog.
"""

import sys

import win32con
import win32print

DC_MINEXTENT = 4
DC_MAXEXTENT = 5


def main(queue):
    handle = win32print.OpenPrinter(queue)
    try:
        info = win32print.GetPrinter(handle, 2)
    finally:
        win32print.ClosePrinter(handle)

    driver = info.get("pDriverName")
    port = info.get("pPortName")

    print(f"queue   : {queue}")
    print(f"driver  : {driver}")
    print(f"port    : {port}")
    print()

    names = win32print.DeviceCapabilities(queue, port, win32con.DC_PAPERNAMES)
    kinds = win32print.DeviceCapabilities(queue, port, win32con.DC_PAPERS)
    sizes = win32print.DeviceCapabilities(queue, port, win32con.DC_PAPERSIZE)

    print(f"forms   : {len(names)} reported")
    print()
    print(f"{'idx':>3}  {'paperkind':>9}  {'width_mm':>8}  {'height_mm':>9}  name")
    print(f"{'-'*3}  {'-'*9}  {'-'*8}  {'-'*9}  {'-'*40}")
    for i, name in enumerate(names):
        kind = kinds[i] if i < len(kinds) else None
        if i < len(sizes):
            # this pywin32 build returns {'x': tenths, 'y': tenths}
            s = sizes[i]
            w, h = (s["x"], s["y"]) if isinstance(s, dict) else s
            w_mm, h_mm = w / 10.0, h / 10.0
        else:
            w_mm = h_mm = 0.0
        print(f"{i:>3}  {kind:>9}  {w_mm:>8.1f}  {h_mm:>9.1f}  {name}")

    print()
    for label, cap in (("min extent", DC_MINEXTENT), ("max extent", DC_MAXEXTENT)):
        try:
            v = win32print.DeviceCapabilities(queue, port, cap)
            if isinstance(v, dict):
                # DC_PAPERSIZE uses x/y, DC_MIN/MAXEXTENT use Width/Length
                x = v.get("x", v.get("Width"))
                y = v.get("y", v.get("Length"))
            else:
                # packed as low word = x, high word = y, in tenths of a mm
                x, y = v & 0xFFFF, (v >> 16) & 0xFFFF
            print(f"{label} : {x/10.0} x {y/10.0} mm  (raw {v})")
        except Exception as exc:
            print(f"{label} : unavailable ({exc})")

    for label, cap in (
        ("orientation", win32con.DC_ORIENTATION),
        ("copies", win32con.DC_COPIES),
        ("colordevice", win32con.DC_COLORDEVICE),
    ):
        try:
            print(f"{label} : {win32print.DeviceCapabilities(queue, port, cap)}")
        except Exception as exc:
            print(f"{label} : unavailable ({exc})")

    try:
        bins = win32print.DeviceCapabilities(queue, port, win32con.DC_BINNAMES)
        print(f"bins        : {bins}")
    except Exception as exc:
        print(f"bins        : unavailable ({exc})")

    print()
    print("DEVMODE defaults")
    devmode = info.get("pDevMode")
    if devmode is None:
        print("  (queue reported no DEVMODE)")
        return
    for field in (
        "PaperSize", "PaperWidth", "PaperLength", "Orientation", "Color",
        "Copies", "PrintQuality", "YResolution", "DefaultSource", "MediaType",
        "Scale", "Fields", "Size", "DriverExtra",
    ):
        try:
            print(f"  {field:<14}= {getattr(devmode, field)}")
        except AttributeError:
            pass


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: caps.py <queue name>")
    main(sys.argv[1])
