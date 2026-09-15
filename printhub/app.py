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

from . import faults, fleet, render

ROOT = pathlib.Path(__file__).resolve().parent.parent
HUB_DIR = pathlib.Path(os.environ.get("HUB_DIR", ROOT))
SPOOL_DIR = HUB_DIR / "spool"
QUEUE = os.environ.get("HUB_QUEUE", "")
DEVMODE_PATH = os.environ.get("HUB_DEVMODE", "")

# Per-printer configuration is read per request, not once at start, because
# the console will be editing it (ENG-3784) and a restart to pick up a
# printer someone just configured would be a poor experience. It is a small
# file. Environment variables keep the read-once rule; this is not one.

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


def _config():
    """Per-printer config, ignoring a read error. Callers that care use
    fleet.load directly and surface the error."""
    return fleet.load(HUB_DIR)[0]


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
        configured=sorted(_config().keys()) or None,
        config_error=fleet.load(HUB_DIR)[1],
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
    """Print to every configured printer at once.

    Shows the product shape: one hub driving whatever is attached, invoked
    from elsewhere. /print stays single-queue per design rule 3.

    Two points worth not undoing. Each printer gets its own card and its own
    blob, because the three have to travel together (Verified 18, 43, 47, 56).
    And rendering happens in child processes, not threads: PDFium is not safe
    to drive concurrently in-process, and a crash would take the agent down.

    dry_run rehearses the whole fan-out without spending media.
    """
    config, config_error = fleet.load(HUB_DIR)
    if config_error:
        return jsonify(error=f"{fleet.CONFIG_NAME} unreadable: {config_error}"), 500

    # Only configured printers, and only ones whose card and blob are actually
    # on disk. A printer with a missing blob would print unpinned and report
    # success, so it is refused by name rather than attempted.
    entries, skipped = [], []
    for queue, entry in config.items():
        resolved, problems = fleet.resolve(HUB_DIR, entry)
        if not resolved.get("devmode") or not resolved.get("card"):
            problems.append("needs both a card and a devmode blob")
        if problems:
            skipped.append({"queue": queue, "why": problems})
            continue
        entries.append({"name": entry.get("label") or queue, "queue": queue,
                        "card": resolved["card"], "devmode": resolved["devmode"]})

    if not entries:
        return jsonify(
            error=f"no usable printers in {fleet.CONFIG_NAME}",
            skipped=skipped,
        ), 500

    dry = request.args.get("dry_run") in ("1", "true", "yes")
    batch = request.args.get("job_id") or str(uuid.uuid4())[:8]
    t0 = time.perf_counter()

    def one(entry):
        started = time.perf_counter() - t0
        cmd = [str(CHILD_PYTHON), "-m", "printhub.render",
               entry["queue"], entry["card"],
               "--devmode", entry["devmode"],
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(entries)) as pool:
        results = list(pool.map(one, entries))

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
    config, config_error = fleet.load(HUB_DIR)

    printers = []
    for q in faults.enumerate_queues():
        # Offline comes from the same enumeration, so it costs nothing extra.
        reading = faults.read(q["queue"], offline=q["offline"])
        entry = config.get(q["queue"], {})
        resolved, problems = fleet.resolve(HUB_DIR, entry)
        reading.update(
            name=entry.get("label") or q["queue"],
            note=entry.get("note"),
            configured=bool(entry),
            pinned=bool(resolved.get("devmode")) and not problems,
            dialog_port=q["dialog_port"],
            duplicate_port=q["duplicate_port"],
            shared=q["shared"],
            network=q["network"],
            config_problems=problems,
        )
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
            "config_error": config_error,
            "configured": sum(1 for p in printers if p["configured"]),
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
