"""
PheedLoop Print Hub - day-one spike rig.

Throwaway code. It exists to answer spikes 1 to 4 of the Windows Print Hub
Spike. Do not let it become the product.

Run it:
    cd C:\\hub
    .\\.venv\\Scripts\\Activate.ps1
    python hub.py                       # dev, single process, reloads off

Or serve it the way the service will:
    waitress-serve --listen=0.0.0.0:8080 hub:app

Configure it with environment variables, so you never edit code to switch
printers:
    HUB_QUEUE     print queue name          REQUIRED
    HUB_DEVMODE   captured DEVMODE blob     strongly recommended
    HUB_DIR       working directory         default C:\\hub

Set HUB_DEVMODE for anything that has to come out the right size. The
exact-scale guarantee below is only as honest as the dpi the driver reports,
and a vendor setting can make that dishonest: setting Zoom-in/out to 105 in
the ZC10L UI makes the driver report 315 dpi instead of 300, and the card
comes out 5 percent oversized while every number the rig prints still looks
correct. Applying a captured blob per job pins it. Capture one with
devmode.py. Writing the queue default instead does not work on this driver,
which re-asserts its own settings within about ten seconds.

Rendering is PDFium, in pdfium_print.py. There is nothing to configure per
job. The page is rendered at the device's own dpi and blitted 1:1, so scale
is exact by construction rather than requested, and the DC comes from the
queue's own default DEVMODE, so whatever was configured by hand in the
vendor driver UI is inherited. That is the same inheritance spike 2 wants.

SumatraPDF is gone, and there is no HUB_RENDERER any more. It could not open
the HUB-CARD queue at all, failing with "Printer with given name doesn't
exist" for every settings string and every flag combination while the same
GDI path succeeded, and it is GPLv3 besides. Do not reintroduce it as a
renderer. To compare output quality, drive it by hand.

Do not point HUB_QUEUE at "Microsoft Print to PDF". That queue opens a
save dialog, and a modal dialog blocks the whole silent print path. Use a
real printer.
"""

import hashlib
import json
import os
import pathlib
import uuid

import win32print
from flask import Flask, jsonify, request

import pdfium_print

HUB_DIR = pathlib.Path(os.environ.get("HUB_DIR", r"C:\hub"))
SPOOL_DIR = HUB_DIR / "spool"
QUEUE = os.environ.get("HUB_QUEUE", "")
DEVMODE_PATH = os.environ.get("HUB_DEVMODE", "")

# Read once at start, like every other setting. A blob that goes missing
# later should not silently turn into an unpinned print.
DEVMODE = None
DEVMODE_ERROR = None
if DEVMODE_PATH:
    try:
        DEVMODE = pathlib.Path(DEVMODE_PATH).read_bytes()
    except OSError as exc:
        DEVMODE_ERROR = f"{type(exc).__name__}: {exc}"

SPOOL_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

# job_id -> state. The dedupe log.
# Spike 6 makes this durable on disk with a 24 hour window. In memory is
# enough to prove the idea today.
seen = {}


def jsonable(value):
    """EnumJobs returns PyTime objects. Make them printable."""
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def queue_error():
    """Return a JSON error when HUB_QUEUE is not set. Fail loudly."""
    if QUEUE:
        return None
    return jsonify(
        error="HUB_QUEUE is not set. Set it to a real printer name.",
        hint='PowerShell: $env:HUB_QUEUE = "HUB-CARD"',
    ), 500


@app.get("/health")
def health():
    return jsonify(
        ok=bool(QUEUE) and DEVMODE_ERROR is None,
        queue=QUEUE or "(not set - set HUB_QUEUE)",
        # Literal. It is here so a stale instance squatting on this port is
        # obvious: an older build answers with a different shape.
        renderer="pdfium",
        devmode=DEVMODE_PATH or None,
        devmode_bytes=len(DEVMODE) if DEVMODE else 0,
        devmode_sha256=(hashlib.sha256(DEVMODE).hexdigest()[:16]
                        if DEVMODE else None),
        devmode_error=DEVMODE_ERROR,
        # Printed size is only trustworthy when a blob pins it. Without one
        # the queue default decides, and the driver can change that under us.
        scale_pinned=DEVMODE is not None,
        hub_dir=str(HUB_DIR),
        jobs_seen=len(seen),
    )


@app.get("/printers")
def printers():
    """Every queue this process can see. Run it as a service too.

    A queue that appears here for you but not for LocalSystem is a
    per-user queue. That is spike 1 failing early, and it is worth
    knowing on day one. queue_visible answers that directly, so nobody has
    to eyeball two lists.
    """
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    raw = win32print.EnumPrinters(flags, None, 4)
    # Level 4 returns dicts in this pywin32 build, not tuples. Indexing
    # p[2] raised KeyError: 2, and only the Session 0 test caught it,
    # because nothing had called this route before.
    names = [p["pPrinterName"] if isinstance(p, dict) else p[2] for p in raw]
    return jsonify(
        printers=names,
        queue=QUEUE or None,
        queue_visible=bool(QUEUE) and QUEUE in names,
    )


@app.post("/print")
def do_print():
    """Accept a PDF and send it to the queue.

    The client generates job_id. Redelivery is normal, not exceptional.
    """
    err = queue_error()
    if err:
        return err

    job_id = request.args.get("job_id") or str(uuid.uuid4())

    if job_id in seen:
        return jsonify(job_id=job_id, state=seen[job_id], deduped=True)

    if "pdf" not in request.files:
        return jsonify(error="POST a PDF as the form field 'pdf'"), 400

    path = SPOOL_DIR / f"{job_id}.pdf"
    request.files["pdf"].save(path)

    # Rendered at the device's own dpi and blitted 1:1, so nothing scales.
    # Measured against HUB-PDF: ink bbox width identical to the source PDF,
    # height one 600 dpi pixel over. Calipers on a real card read both
    # targets exactly, 100.00 and 50.00 mm.
    if DEVMODE_ERROR:
        return jsonify(error=f"HUB_DEVMODE unreadable: {DEVMODE_ERROR}"), 500

    try:
        geo, pages = pdfium_print.print_pdf(
            str(path), QUEUE, doc_name=f"hub {job_id}", devmode=DEVMODE)
    except Exception as exc:
        # PDFium renders in-process, so this is the only thing between a bad
        # PDF and the agent. SumatraPDF's subprocess gave that isolation for
        # free. The shipped agent should render in a child process.
        seen[job_id] = "failed"
        return jsonify(
            job_id=job_id,
            state="failed",
            error=f"{type(exc).__name__}: {exc}",
        ), 500

    # "sent", never "printed". The spooler reports completion when the job
    # leaves the spooler, not when the card lands in the tray. Spike 4
    # decides whether we ever earn the word "printed".
    seen[job_id] = "sent"
    return jsonify(
        job_id=job_id,
        state="sent",
        queue=QUEUE,
        renderer="pdfium",
        scale_pinned=DEVMODE is not None,
        dpi=geo["dpi_x"],
        pages=[{
            "authored_mm": [round(v, 3) for v in p["authored_mm"]],
            "raster_mm": [round(v, 3) for v in p["raster_mm"]],
            "placed_px": list(p["dest_px"]),
            "clipped": p["clipped"],
        } for p in pages],
    )


@app.get("/jobs")
def jobs():
    """Spooler state for the queue. Spike 4 lives here."""
    err = queue_error()
    if err:
        return err
    handle = win32print.OpenPrinter(QUEUE)
    try:
        raw = win32print.EnumJobs(handle, 0, 50, 1)
    finally:
        win32print.ClosePrinter(handle)
    return jsonify([{k: jsonable(v) for k, v in job.items()} for job in raw])


@app.get("/queue")
def queue_info():
    """What the driver reports about its own default settings.

    This is a read, not the DEVMODE capture from spike 2. pywin32 hands
    you a DEVMODE object, not the raw bytes, and the bytes are where the
    driver-private options live. Capture and replay needs a small ctypes
    layer over DocumentProperties. That is day 2.
    """
    err = queue_error()
    if err:
        return err
    handle = win32print.OpenPrinter(QUEUE)
    try:
        info = win32print.GetPrinter(handle, 2)
    finally:
        win32print.ClosePrinter(handle)

    out = {
        "name": info.get("pPrinterName"),
        "driver": info.get("pDriverName"),
        "port": info.get("pPortName"),
        "status": info.get("Status"),
        "jobs_queued": info.get("cJobs"),
    }

    devmode = info.get("pDevMode")
    if devmode is not None:
        for field in ("PaperSize", "PaperWidth", "PaperLength", "Orientation",
                      "Color", "Copies", "PrintQuality", "DefaultSource",
                      "MediaType", "DriverExtra"):
            try:
                out[f"devmode_{field}"] = jsonable(getattr(devmode, field))
            except AttributeError:
                pass

    return jsonify(out)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)