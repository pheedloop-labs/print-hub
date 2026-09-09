"""Render a PDF with PDFium and send it to a Windows print queue over GDI.

Why this exists: SumatraPDF 3.6.1 cannot open the HUB-CARD queue at all. It
fails with "Printer with given name doesn't exist" for every settings string
and every flag combination, while the same Win32/GDI path succeeds and the
same PDF prints correctly by hand. PDFium is also BSD-licensed, which is what
the product should ship anyway.

Scale is exact by construction. The page is rendered at the device's own dpi
and blitted 1:1, so no scaling happens anywhere: no driver "fit to page", no
renderer shrink. That is the `noscale` guarantee, enforced rather than
requested.

The DC is created from the queue's own default DEVMODE, so whatever was
configured by hand in the vendor driver UI is inherited, including the
driver-private bytes. That is the same design Open task 2 wants.

Opens no dialog. Spawns no subprocess.

    pdfium_print.py <queue> <pdf> [--dry-run] [--no-center] [--name NAME]
"""

import ctypes
import ctypes.wintypes as wt
import pathlib

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

# --- GDI device caps ------------------------------------------------------
HORZRES, VERTRES = 8, 10
LOGPIXELSX, LOGPIXELSY = 88, 90
PHYSICALWIDTH, PHYSICALHEIGHT = 110, 111
PHYSICALOFFSETX, PHYSICALOFFSETY = 112, 113

BI_RGB = 0
DIB_RGB_COLORS = 0
SRCCOPY = 0x00CC0020
MM_PER_PT = 25.4 / 72.0


class DOCINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_int),
        ("lpszDocName", wt.LPCWSTR),
        ("lpszOutput", wt.LPCWSTR),
        ("lpszDatatype", wt.LPCWSTR),
        ("fwType", wt.DWORD),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


gdi32.CreateDCW.restype = wt.HDC
gdi32.CreateDCW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR,
                            ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [wt.HDC]
gdi32.GetDeviceCaps.restype = ctypes.c_int
gdi32.GetDeviceCaps.argtypes = [wt.HDC, ctypes.c_int]
gdi32.StartDocW.restype = ctypes.c_int
gdi32.StartDocW.argtypes = [wt.HDC, ctypes.POINTER(DOCINFOW)]
gdi32.StartPage.restype = ctypes.c_int
gdi32.StartPage.argtypes = [wt.HDC]
gdi32.EndPage.restype = ctypes.c_int
gdi32.EndPage.argtypes = [wt.HDC]
gdi32.EndDoc.restype = ctypes.c_int
gdi32.EndDoc.argtypes = [wt.HDC]
gdi32.AbortDoc.restype = ctypes.c_int
gdi32.AbortDoc.argtypes = [wt.HDC]
gdi32.StretchDIBits.restype = ctypes.c_int
gdi32.StretchDIBits.argtypes = [
    wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_void_p, ctypes.POINTER(BITMAPINFOHEADER), ctypes.c_uint,
    wt.DWORD,
]


def load_devmode(devmode):
    """Accept raw bytes or a path, and sanity check the blob.

    Passing a DEVMODE per job is not a nicety on this hardware. The ZC10L
    driver re-asserts its own stored settings over anything written into the
    queue default with SetPrinter, within about ten seconds, so the queue
    default cannot be trusted to hold. A DEVMODE handed straight to CreateDC
    wins and cannot be raced.
    """
    if devmode is None:
        return None
    blob = devmode if isinstance(devmode, (bytes, bytearray)) else \
        pathlib.Path(devmode).read_bytes()
    blob = bytes(blob)
    size = int.from_bytes(blob[68:70], "little")
    extra = int.from_bytes(blob[70:72], "little")
    if size + extra != len(blob):
        raise ValueError(
            f"DEVMODE blob is {len(blob)} bytes but declares dmSize {size} "
            f"+ dmDriverExtra {extra} = {size + extra}")
    name = blob[0:64].decode("utf-16-le", errors="replace").split("\x00")[0]
    return blob, name


def _make_dc(queue, blob):
    buf = ctypes.create_string_buffer(blob, len(blob)) if blob else None
    hdc = gdi32.CreateDCW(None, queue, None, buf)
    if not hdc:
        raise OSError(f"CreateDC failed for {queue!r}: "
                      f"err={ctypes.get_last_error()}")
    return hdc


def device_geometry(queue, devmode=None):
    """Read the queue's printable geometry. Creates and frees a DC only."""
    loaded = load_devmode(devmode)
    hdc = _make_dc(queue, loaded[0] if loaded else None)
    try:
        g = {
            "dpi_x": gdi32.GetDeviceCaps(hdc, LOGPIXELSX),
            "dpi_y": gdi32.GetDeviceCaps(hdc, LOGPIXELSY),
            "printable_px": (gdi32.GetDeviceCaps(hdc, HORZRES),
                             gdi32.GetDeviceCaps(hdc, VERTRES)),
            "physical_px": (gdi32.GetDeviceCaps(hdc, PHYSICALWIDTH),
                            gdi32.GetDeviceCaps(hdc, PHYSICALHEIGHT)),
            "offset_px": (gdi32.GetDeviceCaps(hdc, PHYSICALOFFSETX),
                          gdi32.GetDeviceCaps(hdc, PHYSICALOFFSETY)),
        }
    finally:
        gdi32.DeleteDC(hdc)
    return g


def print_pdf(pdf_path, queue, center=True, doc_name=None, dry_run=False,
              devmode=None):
    """Render every page at device dpi and blit it 1:1 to the queue.

    Returns a list of per-page geometry dicts. With dry_run, computes and
    returns the same geometry without creating a print job.

    devmode takes raw bytes or a path to a captured blob. Pass one whenever
    the printed size has to be trustworthy: the exact-scale guarantee here is
    only as honest as the dpi the driver reports, and a vendor setting can
    make that dishonest. See load_devmode.
    """
    loaded = load_devmode(devmode)
    if loaded:
        blob, blob_device = loaded
        if blob_device.lower() != queue.lower():
            raise ValueError(
                f"DEVMODE blob was captured from {blob_device!r}, not "
                f"{queue!r}. Vendor-private bytes are not portable between "
                f"queues.")
    else:
        blob = None

    geo = device_geometry(queue, blob)
    dpi_x, dpi_y = geo["dpi_x"], geo["dpi_y"]
    if dpi_x != dpi_y:
        raise NotImplementedError(
            f"{queue!r} reports non-square dpi {dpi_x}x{dpi_y}; PDFium takes "
            f"one scale factor, so this needs a per-axis stretch")

    doc = pdfium.PdfDocument(pdf_path)
    pages = []

    hdc = None
    started = False
    try:
        if not dry_run:
            hdc = _make_dc(queue, blob)
            info = DOCINFOW(ctypes.sizeof(DOCINFOW),
                            doc_name or f"hub {pdf_path}", None, None, 0)
            job = gdi32.StartDocW(hdc, ctypes.byref(info))
            if job <= 0:
                raise OSError(f"StartDoc failed: err={ctypes.get_last_error()}")
            started = True

        for index, page in enumerate(doc):
            w_pt, h_pt = page.get_size()
            bmp = page.render(scale=dpi_x / 72.0,
                              force_bitmap_format=pdfium_c.FPDFBitmap_BGRx)
            pw, ph = geo["printable_px"]
            dest_x = (pw - bmp.width) // 2 if center else 0
            dest_y = (ph - bmp.height) // 2 if center else 0

            record = {
                "page": index,
                "authored_mm": (w_pt * MM_PER_PT, h_pt * MM_PER_PT),
                "raster_px": (bmp.width, bmp.height),
                "raster_mm": (bmp.width / dpi_x * 25.4,
                              bmp.height / dpi_y * 25.4),
                "dest_px": (dest_x, dest_y),
                "clipped": bmp.width > pw or bmp.height > ph,
            }
            pages.append(record)

            if dry_run:
                continue

            bmi = BITMAPINFOHEADER(
                ctypes.sizeof(BITMAPINFOHEADER), bmp.width,
                -bmp.height,  # negative height = top-down rows
                1, 32, BI_RGB, bmp.stride * bmp.height, 0, 0, 0, 0)
            gdi32.StartPage(hdc)
            done = gdi32.StretchDIBits(
                hdc, dest_x, dest_y, bmp.width, bmp.height,
                0, 0, bmp.width, bmp.height,
                ctypes.addressof(bmp.buffer), ctypes.byref(bmi),
                DIB_RGB_COLORS, SRCCOPY)
            gdi32.EndPage(hdc)
            if done == 0:
                raise OSError(f"StretchDIBits failed on page {index}: "
                              f"err={ctypes.get_last_error()}")

        if started:
            gdi32.EndDoc(hdc)
            started = False
    finally:
        if hdc:
            if started:
                gdi32.AbortDoc(hdc)
            gdi32.DeleteDC(hdc)

    return geo, pages


def main():
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("queue")
    ap.add_argument("pdf")
    ap.add_argument("--dry-run", action="store_true",
                    help="report geometry, create no print job")
    ap.add_argument("--no-center", action="store_true",
                    help="place at the printable origin instead of centred")
    ap.add_argument("--name", default=None, help="spooler document name")
    ap.add_argument("--devmode", default=None,
                    help="captured DEVMODE blob to apply to this job. Use "
                         "one when the printed size must be trustworthy")
    a = ap.parse_args()

    geo, pages = print_pdf(a.pdf, a.queue, center=not a.no_center,
                           doc_name=a.name, dry_run=a.dry_run,
                           devmode=a.devmode)

    pw, ph = geo["printable_px"]
    print(f"queue         : {a.queue}")
    print(f"devmode       : {a.devmode or '(none - inherits queue default)'}")
    print(f"dpi           : {geo['dpi_x']} x {geo['dpi_y']}")
    print(f"printable px  : {pw} x {ph}")
    print(f"printable mm  : {pw/geo['dpi_x']*25.4:.2f} x "
          f"{ph/geo['dpi_y']*25.4:.2f}")
    print(f"offset px     : {geo['offset_px']}")
    print(f"mode          : {'DRY RUN, nothing spooled' if a.dry_run else 'PRINTED'}")
    for p in pages:
        aw, ah = p["authored_mm"]
        rw, rh = p["raster_mm"]
        print(f"  page {p['page']}: authored {aw:.2f} x {ah:.2f} mm  ->  "
              f"raster {p['raster_px'][0]} x {p['raster_px'][1]} px = "
              f"{rw:.2f} x {rh:.2f} mm")
        print(f"          scale error {rw-aw:+.3f} x {rh-ah:+.3f} mm, "
              f"placed at {p['dest_px']}, clipped={p['clipped']}")


if __name__ == "__main__":
    main()
