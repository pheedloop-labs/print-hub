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

Rendering is PDFium, in pdfium_print.py. The page is rendered at the
device's own dpi and blitted 1:1, so scale is exact by construction rather
than requested.

With no blob the DC comes from the queue's own default DEVMODE, so whatever
was configured by hand is inherited. Do not rely on that: the queue default
is exactly what a driver UI change moves under you, and on five printers
tested it has silently produced a 5 percent oversized card, a badge that
never cuts, and a page cropped to 306 of its 696 rows after somebody
reinstalled a printer. Pin a captured blob. It is a configuration backup as
much as a settings pin.

SumatraPDF is gone, and there is no HUB_RENDERER any more. It could not open
the HUB-CARD queue at all, failing with "Printer with given name doesn't
exist" for every settings string and every flag combination while the same
GDI path succeeded, and it is GPLv3 besides. Do not reintroduce it as a
renderer. To compare output quality, drive it by hand.

Do not point HUB_QUEUE at "Microsoft Print to PDF". That queue opens a
save dialog, and a modal dialog blocks the whole silent print path. Use a
real printer.
"""

import concurrent.futures
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
import uuid

import win32print
from flask import Flask, jsonify, request

import pdfium_print

HUB_DIR = pathlib.Path(os.environ.get("HUB_DIR", r"C:\hub"))
SPOOL_DIR = HUB_DIR / "spool"
QUEUE = os.environ.get("HUB_QUEUE", "")
DEVMODE_PATH = os.environ.get("HUB_DEVMODE", "")

# The fleet, for /demo only. Optional: absent or malformed just disables the
# route. /print is untouched and still drives exactly one queue.
FLEET = []
FLEET_ERROR = None
try:
    _cfg = json.loads((HUB_DIR / "printers.json").read_text(encoding="utf-8"))
    FLEET = _cfg.get("printers", [])
except (OSError, ValueError) as exc:
    FLEET_ERROR = f"{type(exc).__name__}: {exc}"

# The venv interpreter, because /demo renders in child processes and under
# the service sys.executable is waitress-serve.exe rather than python.
CHILD_PYTHON = pathlib.Path(sys.prefix) / "Scripts" / "python.exe"
if not CHILD_PYTHON.exists():
    CHILD_PYTHON = pathlib.Path(sys.executable)

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
        # /demo only. /print still drives exactly one queue, per design rule 3.
        fleet=[f["name"] for f in FLEET] or None,
        fleet_error=FLEET_ERROR,
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


@app.post("/demo")
def demo():
    """Print to every printer in the fleet at once. One request, five badges.

    Why this route exists at all, given HUB_QUEUE is deliberately single: a
    demo has to show the product shape, which is one hub on a venue network
    driving whatever printers are attached, invoked from somewhere else.
    /print stays exactly as it was.

    Two design points worth not undoing.

    Each printer gets **its own card and its own blob**, from printers.json.
    A page authored for another device is clipped or rescaled and neither is
    visible by eye, and an unpinned job inherits whatever the driver UI was
    last set to. The three have to travel together.

    Rendering happens in **child processes**, one per printer, not threads.
    PDFium runs in-process and is not safe to drive concurrently from one
    process, and a crash would take the whole agent down with it. This is
    also the child-process isolation the shipped agent wants anyway, so the
    route doubles as a demonstration of it.

    Still reports "sent", never "printed". Nothing here can confirm a badge
    exists; five printers cannot do together what none can do alone.
    """
    if FLEET_ERROR:
        return jsonify(error=f"printers.json unreadable: {FLEET_ERROR}"), 500
    if not FLEET:
        return jsonify(error="no printers configured in printers.json"), 500

    # Rehearse the whole fan-out without spending media. Worth having on a
    # demo route: the first live run of this cost a PVC card to discover a
    # printer was on the wrong USB port.
    dry = request.args.get("dry_run") in ("1", "true", "yes")

    batch = request.args.get("job_id") or str(uuid.uuid4())[:8]
    t0 = time.perf_counter()

    def one(entry):
        started = time.perf_counter() - t0
        cmd = [str(CHILD_PYTHON), str(HUB_DIR / "pdfium_print.py"),
               entry["queue"], entry["card"],
               "--devmode", entry["devmode"],
               "--name", f"demo-{batch}-{entry['name']}"]
        if dry:
            cmd.append("--dry-run")
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return {"name": entry["name"], "queue": entry["queue"],
                    "state": "failed", "error": "timed out after 120 s"}
        out = p.stdout
        geo = next((l.strip() for l in out.splitlines() if "raster" in l), "")
        return {
            "name": entry["name"],
            "queue": entry["queue"],
            "state": "sent" if p.returncode == 0 else "failed",
            "launched_ms": round(started * 1000, 1),
            "took_ms": round((time.perf_counter() - t0 - started) * 1000, 1),
            "clipped": "clipped=True" in out,
            "geometry": geo or None,
            "error": (p.stderr.strip()[:300] or None) if p.returncode else None,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(FLEET)) as pool:
        results = list(pool.map(one, FLEET))

    wall = time.perf_counter() - t0
    sent = sum(1 for r in results if r["state"] == "sent")
    seen[f"demo-{batch}"] = "sent" if sent == len(results) else "partial"
    return jsonify(
        batch=batch,
        state=("dry_run" if dry else
               "sent" if sent == len(results) else "partial"),
        dry_run=dry,
        sent=sent,
        of=len(results),
        wall_ms=round(wall * 1000, 1),
        # Sum against wall clock is the parallelism. Measured 3.4x on five.
        serial_ms=round(sum(r.get("took_ms", 0) for r in results), 1),
        printers=results,
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

    The status integer is the useful field here: 16 out of cards, 8 jammed,
    262144 no ribbon, 4194304 cover open, 2 a generic error on drivers that
    do not attribute their faults.

    **The devmode_* fields below are the stored default and can be stale.**
    They come from GetPrinter level 2 pDevMode. After the Brother's form was
    changed to 62mm by hand, that source still reported the previous form's
    29 mm width while dmPaperSize had correctly moved on, and the DYMO kept
    a form *name* from two media changes earlier. DocumentProperties, which
    devmode.py reads, resolves correctly and matches what CreateDC builds.
    Trust these for a rough look and never for geometry.
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