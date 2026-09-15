"""PheedLoop Print Hub - spike rig. Flask over a PDFium/GDI print path.

Throwaway code answering spikes 1 to 4. Do not let it become the product.
The findings, the evidence and the traps are in CLAUDE.MD; this file keeps
only what a reader needs to follow the code.

Configure with environment variables, never by editing code:

    HUB_QUEUE     print queue name           REQUIRED (design rule 3)
    HUB_DEVMODE   captured DEVMODE blob      strongly recommended
    HUB_DIR       working directory          default: the repo root

Set HUB_DEVMODE for anything that has to come out the right size. Unpinned
jobs inherit the queue default, which a driver UI change moves under you, and
that has silently produced a 5% oversized card, an uncut badge and a page
cropped to 306 of 696 rows (CLAUDE.MD Verified 18, 43, 47, 56).

Do not point HUB_QUEUE at "Microsoft Print to PDF": it opens a save dialog,
and a modal dialog blocks the whole silent print path (design rule 5).
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
from flask import Flask, jsonify, request, send_from_directory

from . import faults, render

ROOT = pathlib.Path(__file__).resolve().parent.parent
HUB_DIR = pathlib.Path(os.environ.get("HUB_DIR", ROOT))
SPOOL_DIR = HUB_DIR / "spool"
QUEUE = os.environ.get("HUB_QUEUE", "")
DEVMODE_PATH = os.environ.get("HUB_DEVMODE", "")

# The fleet, for /demo only. Absent or malformed just disables the route.
FLEET = []
FLEET_ERROR = None
try:
    _cfg = json.loads((HUB_DIR / "printers.json").read_text(encoding="utf-8"))
    FLEET = _cfg.get("printers", [])
except (OSError, ValueError) as exc:
    FLEET_ERROR = f"{type(exc).__name__}: {exc}"

# /demo renders in child processes, and under the service sys.executable is
# waitress-serve.exe rather than python.
CHILD_PYTHON = pathlib.Path(sys.prefix) / "Scripts" / "python.exe"
if not CHILD_PYTHON.exists():
    CHILD_PYTHON = pathlib.Path(sys.executable)

# Read once at start. A blob that goes missing later must not silently turn
# into an unpinned print.
DEVMODE = None
DEVMODE_ERROR = None
if DEVMODE_PATH:
    try:
        DEVMODE = pathlib.Path(DEVMODE_PATH).read_bytes()
    except OSError as exc:
        DEVMODE_ERROR = f"{type(exc).__name__}: {exc}"

SPOOL_DIR.mkdir(parents=True, exist_ok=True)

# static/ is the built console, emitted by `cd console && npm run build`.
# static_url_path="" serves its assets from the root, so the built index.html
# needs no <base> and dev and production resolve the same paths. The explicit
# API routes below are more specific than the static catch-all and still win.
app = Flask(__name__, static_folder="static", static_url_path="")

# job_id -> state. In memory; making it durable with a 24 h window is task 2.
seen = {}


def jsonable(value):
    """EnumJobs returns PyTime objects. Make them printable."""
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def queue_error():
    """JSON error when HUB_QUEUE is not set. Fail loudly, never default."""
    if QUEUE:
        return None
    return jsonify(
        error="HUB_QUEUE is not set. Set it to a real printer name.",
        hint='PowerShell: $env:HUB_QUEUE = "HUB-CARD"',
    ), 500


@app.get("/")
def console():
    """The console, if it has been built.

    Says so plainly when it has not, rather than 404ing: a hub serving a
    missing console should not look like a hub that is down.
    """
    index = pathlib.Path(app.static_folder) / "index.html"
    if not index.exists():
        return jsonify(
            error="The console has not been built.",
            hint="cd console && npm install && npm run build",
        ), 503
    return send_from_directory(app.static_folder, "index.html")


@app.get("/health")
def health():
    return jsonify(
        ok=bool(QUEUE) and DEVMODE_ERROR is None,
        queue=QUEUE or "(not set - set HUB_QUEUE)",
        # Literal, so a stale instance squatting on this port is obvious.
        renderer="pdfium",
        devmode=DEVMODE_PATH or None,
        devmode_bytes=len(DEVMODE) if DEVMODE else 0,
        devmode_sha256=(hashlib.sha256(DEVMODE).hexdigest()[:16]
                        if DEVMODE else None),
        devmode_error=DEVMODE_ERROR,
        # Printed size is only trustworthy when a blob pins it.
        scale_pinned=DEVMODE is not None,
        hub_dir=str(HUB_DIR),
        jobs_seen=len(seen),
        fleet=[f["name"] for f in FLEET] or None,
        fleet_error=FLEET_ERROR,
    )


@app.get("/printers")
def printers():
    """Every queue this process can see.

    queue_visible answers the per-user question directly. An enumerated queue
    is not necessarily a usable one - see the orphan Epson in CLAUDE.MD.
    """
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    raw = win32print.EnumPrinters(flags, None, 4)
    # Level 4 returns dicts in this pywin32 build, not tuples.
    names = [p["pPrinterName"] if isinstance(p, dict) else p[2] for p in raw]
    return jsonify(
        printers=names,
        queue=QUEUE or None,
        queue_visible=bool(QUEUE) and QUEUE in names,
    )


@app.post("/print")
def do_print():
    """Accept a PDF and send it to the queue.

    The client generates job_id; redelivery is normal (design rule 1).
    Reports "sent", never "printed": nothing here can confirm a card exists
    (design rule 2, Verified 29).
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

    if DEVMODE_ERROR:
        return jsonify(error=f"HUB_DEVMODE unreadable: {DEVMODE_ERROR}"), 500

    try:
        geo, pages = render.print_pdf(
            str(path), QUEUE, doc_name=f"hub {job_id}", devmode=DEVMODE)
    except Exception as exc:
        # PDFium renders in-process here, so this is the only thing between a
        # bad PDF and the agent. /demo already renders in a child process;
        # bringing that to this route is later-task 1.
        seen[job_id] = "failed"
        return jsonify(
            job_id=job_id,
            state="failed",
            error=f"{type(exc).__name__}: {exc}",
        ), 500

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
    """Print to every printer in printers.json at once.

    Shows the product shape: one hub driving whatever is attached, invoked
    from elsewhere. /print stays single-queue per design rule 3.

    Two points worth not undoing. Each printer gets its own card and its own
    blob, because the three have to travel together (Verified 18, 43, 47, 56).
    And rendering happens in child processes, not threads: PDFium is not safe
    to drive concurrently in-process, and a crash would take the agent down.

    dry_run rehearses the whole fan-out without spending media.
    """
    if FLEET_ERROR:
        return jsonify(error=f"printers.json unreadable: {FLEET_ERROR}"), 500
    if not FLEET:
        return jsonify(error="no printers configured in printers.json"), 500

    dry = request.args.get("dry_run") in ("1", "true", "yes")
    batch = request.args.get("job_id") or str(uuid.uuid4())[:8]
    t0 = time.perf_counter()

    def one(entry):
        started = time.perf_counter() - t0
        cmd = [str(CHILD_PYTHON), "-m", "printhub.render",
               entry["queue"], str(HUB_DIR / entry["card"]),
               "--devmode", str(HUB_DIR / entry["devmode"]),
               "--name", f"demo-{batch}-{entry['name']}"]
        if dry:
            cmd.append("--dry-run")
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=120, cwd=str(ROOT))
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


@app.get("/api/state")
def api_state():
    """Everything the console's printer view needs, in one poll.

    One call rather than one per printer: the console is read from a phone
    on venue wifi, where five round trips is meaningfully worse than one.

    Nothing here ever reports a printer as ready. `idle` means no fault was
    reported, which is not the same claim - see printhub.faults.
    """
    entries = FLEET
    if not entries and QUEUE:
        entries = [{"name": QUEUE, "queue": QUEUE}]

    # One WMI query for the whole fleet. None means WMI could not be asked,
    # which is not the same as nothing being offline, so it is passed through
    # rather than flattened to False.
    offline = faults.offline_queues()

    printers = []
    for entry in entries:
        is_offline = None if offline is None else entry["queue"] in offline
        reading = faults.read(entry["queue"], offline=is_offline)
        reading["name"] = entry.get("name") or entry["queue"]
        reading["note"] = entry.get("note")
        printers.append(reading)

    return jsonify(
        hub={
            "queue": QUEUE or None,
            "scale_pinned": DEVMODE is not None,
            "devmode_sha256": (hashlib.sha256(DEVMODE).hexdigest()[:16]
                               if DEVMODE else None),
            "devmode_error": DEVMODE_ERROR,
            "renderer": "pdfium",
            "jobs_seen": len(seen),
            "fleet_error": FLEET_ERROR,
        },
        printers=printers,
        polled_at=time.time(),
    )


@app.get("/jobs")
def jobs():
    """Spooler job state for the queue."""
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
    """What the driver reports about itself.

    status is the useful field: 16 out of cards, 8 jammed, 262144 no ribbon,
    4194304 cover open, 2 a generic error on drivers that do not attribute.

    The devmode_* fields come from GetPrinter level 2 and can be stale
    (Verified 35, 44, 51). Rough look only, never geometry - printhub.devmode
    resolves correctly via DocumentProperties.
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
