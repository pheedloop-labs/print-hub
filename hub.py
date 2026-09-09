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
    HUB_RENDERER  "pdfium" or "sumatra"     default "pdfium"
    HUB_MEDIA     paper size for Sumatra    default "" (queue default)
    HUB_COLOR     "color" or "monochrome"   default "color"
    HUB_SUMATRA   path to SumatraPDF.exe
    HUB_DIR       working directory         default C:\\hub

HUB_MEDIA and HUB_COLOR apply to the SumatraPDF path only. The PDFium path
inherits the queue's own default DEVMODE instead, which is what spike 2
wants anyway, so there is nothing to pass per job.

SumatraPDF cannot print to the ZC10L queue at all: it fails with "Printer
with given name doesn't exist" for every settings string and every flag
combination, while the same GDI path succeeds. So "pdfium" is the default.
Keep "sumatra" selectable for the bake-off, not for card printing.

Do not point HUB_QUEUE at "Microsoft Print to PDF". That queue opens a
save dialog, and a modal dialog blocks the whole silent print path. Use a
real printer.
"""

import json
import os
import pathlib
import subprocess
import uuid

import win32print
from flask import Flask, jsonify, request

import pdfium_print

HUB_DIR = pathlib.Path(os.environ.get("HUB_DIR", r"C:\hub"))
SPOOL_DIR = HUB_DIR / "spool"
QUEUE = os.environ.get("HUB_QUEUE", "")
RENDERER = os.environ.get("HUB_RENDERER", "pdfium").lower()
MEDIA = os.environ.get("HUB_MEDIA", "")
COLOR = os.environ.get("HUB_COLOR", "color")
SUMATRA = os.environ.get(
    "HUB_SUMATRA", r"C:\Program Files\SumatraPDF\SumatraPDF.exe"
)

SPOOL_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

# job_id -> state. The dedupe log.
# Spike 6 makes this durable on disk with a 24 hour window. In memory is
# enough to prove the idea today.
seen = {}


def print_settings():
    """Build the SumatraPDF -print-settings string."""
    parts = ["noscale"]
    if MEDIA:
        parts.append(f"paper={MEDIA}")
    if COLOR:
        parts.append(COLOR)
    return ",".join(parts)


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
        ok=bool(QUEUE) and RENDERER in ("pdfium", "sumatra"),
        queue=QUEUE or "(not set - set HUB_QUEUE)",
        renderer=RENDERER,
        settings=print_settings() if RENDERER == "sumatra" else "(queue default DEVMODE)",
        sumatra=SUMATRA,
        sumatra_found=pathlib.Path(SUMATRA).exists(),
        hub_dir=str(HUB_DIR),
        jobs_seen=len(seen),
    )


@app.get("/printers")
def printers():
    """Every queue this process can see. Run it as a service too.

    A queue that appears here for you but not for LocalSystem is a
    per-user queue. That is spike 1 failing early, and it is worth
    knowing on day one.
    """
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return jsonify([p[2] for p in win32print.EnumPrinters(flags, None, 4)])


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

    if RENDERER == "pdfium":
        # Rendered at the device's own dpi and blitted 1:1, so nothing
        # scales. Measured against HUB-PDF: ink bbox width identical to the
        # source, height one 600 dpi pixel over. Calipers on a real card read
        # both targets exactly.
        try:
            geo, pages = pdfium_print.print_pdf(
                str(path), QUEUE, doc_name=f"hub {job_id}")
        except Exception as exc:
            seen[job_id] = "failed"
            return jsonify(
                job_id=job_id,
                state="failed",
                renderer="pdfium",
                error=f"{type(exc).__name__}: {exc}",
            ), 500

        seen[job_id] = "sent"
        return jsonify(
            job_id=job_id,
            state="sent",
            queue=QUEUE,
            renderer="pdfium",
            dpi=geo["dpi_x"],
            pages=[{
                "authored_mm": [round(v, 3) for v in p["authored_mm"]],
                "raster_mm": [round(v, 3) for v in p["raster_mm"]],
                "placed_px": list(p["dest_px"]),
                "clipped": p["clipped"],
            } for p in pages],
        )

    if RENDERER != "sumatra":
        return jsonify(
            error=f"HUB_RENDERER={RENDERER!r} is not a renderer",
            hint='use "pdfium" or "sumatra"',
        ), 500

    if not pathlib.Path(SUMATRA).exists():
        return jsonify(error=f"SumatraPDF not found at {SUMATRA}"), 500

    cmd = [
        SUMATRA,
        "-print-to", QUEUE,
        "-print-settings", print_settings(),
        "-silent",
        "-exit-when-done",
        str(path),
    ]

    try:
        result = subprocess.run(cmd, timeout=90, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        seen[job_id] = "timeout"
        return jsonify(job_id=job_id, state="timeout", cmd=cmd), 504

    if result.returncode != 0:
        seen[job_id] = "failed"
        return jsonify(
            job_id=job_id,
            state="failed",
            returncode=result.returncode,
            stderr=(result.stderr or "")[:2000],
            cmd=cmd,
        ), 500

    # "sent", never "printed". The spooler reports completion when the job
    # leaves the spooler, not when the card lands in the tray. Spike 4
    # decides whether we ever earn the word "printed".
    seen[job_id] = "sent"
    return jsonify(job_id=job_id, state="sent", queue=QUEUE,
                   renderer="sumatra", settings=print_settings())


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