"""Collect one benchmark row per print queue, for comparing printers.

Written when the spike turned into a printer bake-off. Every field here was
previously gathered by hand from caps.py, a geometry probe and devmode.py,
three times over, and getting a new printer onto the comparison table should
not cost that again.

Objective fields only. Fault behaviour, recovery and dialog habits cannot be
read from a driver, they have to be induced on hardware, so those live in
printer-benchmark.html alongside these numbers.

    benchmark.py            all local queues
    benchmark.py "<queue>"  just one
    benchmark.py --json     machine readable

Read only. Opens no dialog, spools nothing.
"""

import ctypes
import json
import math
import sys
from ctypes import wintypes as wt

import win32con
import win32print

import devmode as dm

g32 = ctypes.WinDLL("gdi32", use_last_error=True)
g32.CreateDCW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, wt.LPVOID]
g32.CreateDCW.restype = wt.HDC
g32.GetDeviceCaps.argtypes = [wt.HDC, ctypes.c_int]   # HDC overflows plain int
g32.GetDeviceCaps.restype = ctypes.c_int
g32.DeleteDC.argtypes = [wt.HDC]

CAPS = {"mm_x": 4, "mm_y": 6, "px_x": 8, "px_y": 10, "dpi_x": 88, "dpi_y": 90,
        "phys_x": 110, "phys_y": 111, "off_x": 112, "off_y": 113}
DC_MINEXTENT, DC_MAXEXTENT, DC_COLORDEVICE = 4, 5, 32


def author_size(px, dpi):
    """Largest mm, to 2 dp, whose PDFium raster is exactly px wide.

    PDFium rounds its raster up, so authoring at the exact imageable size
    overshoots by a pixel and pdfium_print reports clipped=True. This is the
    number to hand make-test-card.py.
    """
    mm = px / dpi * 25.4
    for step in range(40):
        cand = math.floor((mm - step * 0.01) * 100) / 100
        if math.ceil(cand / 25.4 * dpi) == px:
            return cand
    return None


def row(queue):
    h = win32print.OpenPrinter(queue)
    try:
        info = win32print.GetPrinter(h, 2)
    finally:
        win32print.ClosePrinter(h)
    port = info.get("pPortName")
    r = {"queue": queue, "driver": info.get("pDriverName"), "port": port}

    dc = g32.CreateDCW(None, queue, None, None)
    if dc:
        try:
            c = {k: g32.GetDeviceCaps(dc, v) for k, v in CAPS.items()}
        finally:
            g32.DeleteDC(dc)
        r.update(c)
        r["full_bleed"] = c["off_x"] == 0 and c["off_y"] == 0 \
            and c["phys_x"] == c["px_x"] and c["phys_y"] == c["px_y"]
        if c["dpi_x"] and c["dpi_y"]:
            r["implied_mm_x"] = round(c["px_x"] / c["dpi_x"] * 25.4, 2)
            r["implied_mm_y"] = round(c["px_y"] / c["dpi_y"] * 25.4, 2)
            r["mm_delta_x"] = round(abs(r["implied_mm_x"] - c["mm_x"]), 2)
            r["mm_delta_y"] = round(abs(r["implied_mm_y"] - c["mm_y"]), 2)
            r["author_mm"] = [author_size(c["px_x"], c["dpi_x"]),
                              author_size(c["px_y"], c["dpi_y"])]
    else:
        r["createdc"] = f"FAILED err={ctypes.get_last_error()}"

    try:
        blob = dm.capture(queue)
        d = dm.describe(blob)
        r["devmode_public"] = d.get("dmSize")
        r["devmode_private"] = d.get("dmDriverExtra")
        r["devmode_total"] = len(blob)
        r["form"] = d.get("form") or "(unnamed)"
        r["paperkind"] = d.get("paper_size")
        r["dm_color"] = d.get("color")
    except Exception as exc:
        r["devmode"] = f"FAILED {type(exc).__name__}: {exc}"

    def cap(which, label):
        try:
            return win32print.DeviceCapabilities(queue, port, which)
        except Exception:
            return None

    names = cap(win32con.DC_PAPERNAMES, "forms")
    r["forms"] = len(names) if names else 0
    r["colordevice"] = cap(DC_COLORDEVICE, "colordevice")
    for key, which in (("min_extent", DC_MINEXTENT), ("max_extent", DC_MAXEXTENT)):
        v = cap(which, key)
        if isinstance(v, dict):
            r[key] = [v.get("Width", 0) / 10, v.get("Length", 0) / 10]
    bins = cap(win32con.DC_BINNAMES, "bins")
    r["bins"] = list(bins) if bins else None
    return r


args = [a for a in sys.argv[1:] if a != "--json"]
as_json = "--json" in sys.argv
queues = args or sorted(
    p["pPrinterName"] for p in win32print.EnumPrinters(
        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS,
        None, 4))

rows = []
for q in queues:
    try:
        rows.append(row(q))
    except Exception as exc:
        rows.append({"queue": q, "error": f"{type(exc).__name__}: {exc}"})

if as_json:
    print(json.dumps(rows, indent=2))
else:
    for r in rows:
        print(f"=== {r['queue']}")
        for k, v in r.items():
            if k != "queue":
                print(f"    {k:<16} {v}")
        print()
