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
import socket
import subprocess
import sys
import time
import uuid

import win32print
from flask import Flask, jsonify, request, send_from_directory

from . import (faults, fleet, identity as identity_mod,
               journal as journal_mod, render, watcher as watcher_mod)

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

# The job record, and the only thing that polls fast enough to feed it. The
# spooler shows a job for about 1.4 s, so the watcher runs at 0.5 s and
# everything else reads what it saw. Dedupe lives here too and is now durable
# across a restart, which design rule 1 needs and an in-memory dict never
# gave: the service recycles on every code change.
JOURNAL = journal_mod.Journal(HUB_DIR)
WATCHER = watcher_mod.Watcher(JOURNAL)
WATCHER.start()

# Stable ids for this hub and its printers, for the OnSite app to address.
IDENTITY = identity_mod.Identity(HUB_DIR)
API_VERSION = "1"
PORT = 8080


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


def offline_refusal(queue):
    """Refuse a job to a printer Windows reports offline. None means proceed.

    The spike's one reusable lesson about detection is that a check is only
    worth having if it compares two sources that can disagree (Verified 57),
    and its one consequence is that the agent should refuse what it can
    detect. Offline became detectable for 2 ms (Verified 58), so this is the
    second member of that family after `clipped`.

    Without it the hub returns `sent`, with correct geometry, for a printer
    that is switched off - which it has now done three separate times in this
    project. One honest error beats a badge that does not exist.

    Two limits worth stating rather than hiding. The flag takes about 20
    seconds to appear, so a printer unplugged a moment ago still passes here;
    this narrows the window, it does not close it. And `paused` is
    deliberately NOT refused: a paused queue holds the job and prints it on
    resume, so the job is delayed rather than lost.
    """
    for q in faults.enumerate_queues():
        if q["queue"] != queue:
            continue
        if q["dialog_port"]:
            # Design rule 5. This queue prompts for a filename, and a modal
            # dialog on a machine with no screen is an outage that blocks the
            # whole print path until somebody clicks it. Never reachable.
            return jsonify(
                state="refused",
                reason="opens_dialog",
                queue=queue,
                error=(f"{queue} prompts for a filename and would hang the "
                       f"print path on a machine with no screen. It cannot be "
                       f"printed to."),
            ), 409
        if q["offline"]:
            return jsonify(
                state="refused",
                reason="offline",
                queue=queue,
                error=(f"{queue} is reported offline, so this job would be "
                       f"accepted and never printed. Check the printer is on "
                       f"and connected, then send it again."),
            ), 409
        return None
    return jsonify(
        state="refused",
        reason="unknown_queue",
        queue=queue,
        error=f"{queue} is not a print queue on this machine.",
    ), 404


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
        jobs_seen=JOURNAL.count(),
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

    prior = JOURNAL.seen(job_id)
    if prior:
        # Redelivery is normal, not exceptional (design rule 1), and this now
        # survives a restart, which the old in-memory log did not.
        return jsonify(job_id=job_id, state=prior["state"], deduped=True,
                       first_seen=prior["first_seen"])

    # Refuse before taking the file: a job we will not print is not accepted.
    refusal = offline_refusal(QUEUE)
    if refusal:
        JOURNAL.record("refused", job_id=job_id, queue=QUEUE,
                       source=request.remote_addr,
                       detail=refusal[0].get_json()["error"])
        return refusal

    if "pdf" not in request.files:
        return jsonify(error="POST a PDF as the form field 'pdf'"), 400

    path = SPOOL_DIR / f"{job_id}.pdf"
    request.files["pdf"].save(path)

    if DEVMODE_ERROR:
        return jsonify(error=f"HUB_DEVMODE unreadable: {DEVMODE_ERROR}"), 500

    # Recorded before the render, not after: a crash in PDFium would
    # otherwise leave no trace of a job the hub had already taken.
    JOURNAL.record("accepted", job_id=job_id, queue=QUEUE,
                   label=_config().get(QUEUE, {}).get("label"),
                   source=request.remote_addr,
                   detail="Accepted over HTTP")

    try:
        geo, pages = render.print_pdf(
            str(path), QUEUE, doc_name=f"hub {job_id}", devmode=DEVMODE)
    except Exception as exc:
        # PDFium renders in-process here, so this is the only thing between a
        # bad PDF and the agent. /demo already renders in a child process;
        # bringing that to this route is later-task 1.
        JOURNAL.record("failed", job_id=job_id, queue=QUEUE,
                       detail=f"{type(exc).__name__}: {exc}")
        return jsonify(
            job_id=job_id,
            state="failed",
            error=f"{type(exc).__name__}: {exc}",
        ), 500

    # "sent", never "printed". The watcher may add spooled/cleared on top,
    # but it polls at 0.5 s and a fast printer can beat it, so this is the
    # event that always happens. None of it implies a badge exists.
    JOURNAL.record(
        "sent", job_id=job_id, queue=QUEUE,
        detail=f"Renderer finished, {len(pages)} page(s) handed to the spooler",
        geometry={"dpi": geo["dpi_x"],
                  "raster_mm": [round(v, 2) for v in pages[0]["raster_mm"]],
                  "clipped": any(p["clipped"] for p in pages),
                  "scale_pinned": DEVMODE is not None},
    )
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
    JOURNAL.record("accepted", job_id=f"demo-{batch}", queue="(fan-out)",
                   label="demo", source=request.remote_addr,
                   detail=f"{sent} of {len(results)} printers accepted")
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

    # Read the watcher's last snapshot rather than polling the spooler again.
    # It is at most half a second old, it is the same reading that fed the job
    # record, and it means the console and the record can never disagree.
    snap = WATCHER.snapshot()
    if snap is None:
        readings = [faults.read(q["queue"], offline=q["offline"])
                    for q in faults.enumerate_queues()]
        polled_at = time.time()
    else:
        readings = snap["printers"]
        polled_at = snap["at"]

    printers = []
    for reading in readings:
        # Copy: the snapshot belongs to the watcher and is shared between
        # requests. Updating it in place would leak this request's config
        # into the next one's reading.
        row = dict(reading)
        entry = config.get(row["queue"], {})
        resolved, problems = fleet.resolve(HUB_DIR, entry)
        row.update(
            name=entry.get("label") or row["queue"],
            note=entry.get("note"),
            configured=bool(entry),
            pinned=bool(resolved.get("devmode")) and not problems,
            config_problems=problems,
        )
        printers.append(row)

    return jsonify(
        hub={
            "queue": QUEUE or None,
            "scale_pinned": DEVMODE is not None,
            "devmode_sha256": (hashlib.sha256(DEVMODE).hexdigest()[:16]
                               if DEVMODE else None),
            "devmode_error": DEVMODE_ERROR,
            "renderer": "pdfium",
            "jobs_seen": JOURNAL.count(),
            "config_error": config_error,
            "configured": sum(1 for p in printers if p["configured"]),
        },
        printers=printers,
        polled_at=polled_at,
        watching=snap is not None,
    )


@app.get("/api/jobs")
def api_jobs():
    """The job record: what the hub was asked to print and what followed.

    Not the live queue. A job is in the spooler for about 1.4 s, so the queue
    empties faster than anyone can look at it. These are the watcher's
    observations, kept per day and reloaded on start.

    No entry here ever says printed. `cleared` means the job left the
    spooler, which happens whether or not media emerged.
    """
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify(jobs=JOURNAL.recent(limit), total=JOURNAL.count())


@app.post("/api/test-page")
def api_test_page():
    """Send a printer its own calibration card.

    This is the only way to see whether a printer is well: no fault is
    visible while a queue is idle, so the honest test is to send something
    and watch (Verified 29). It spends real media, which is why it is an
    explicit action rather than anything automatic.

    Refuses rather than guesses. A card authored for another device is
    clipped or rescaled and neither is visible by eye, and an unpinned job
    inherits whatever the driver UI was last set to.
    """
    queue = request.args.get("queue") or ""
    config, config_error = fleet.load(HUB_DIR)
    if config_error:
        return jsonify(error=f"{fleet.CONFIG_NAME} unreadable: {config_error}"), 500

    entry = config.get(queue)
    if not entry:
        return jsonify(error=f"{queue!r} is not configured on this hub"), 400

    refusal = offline_refusal(queue)
    if refusal:
        return refusal

    resolved, problems = fleet.resolve(HUB_DIR, entry)
    if not resolved.get("card"):
        problems.append("no test card configured")
    if not resolved.get("devmode"):
        problems.append("no DEVMODE blob configured, so the size would not be trustworthy")
    if problems:
        return jsonify(error="refusing to print", problems=problems), 400

    job_id = f"test-{uuid.uuid4().hex[:8]}"
    JOURNAL.record("accepted", job_id=job_id, queue=queue,
                   label=entry.get("label"), source=request.remote_addr,
                   detail="Test page requested from the console")

    # Child process, like /demo: PDFium is not safe to drive concurrently
    # in-process and a bad render would take the agent down with it.
    cmd = [str(CHILD_PYTHON), "-m", "printhub.render",
           queue, resolved["card"], "--devmode", resolved["devmode"],
           "--name", f"hub {job_id}"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                           cwd=str(ROOT))
    except subprocess.TimeoutExpired:
        JOURNAL.record("failed", job_id=job_id, queue=queue,
                       detail="Renderer timed out after 120 s")
        return jsonify(job_id=job_id, state="failed",
                       error="timed out after 120 s"), 500

    if p.returncode != 0:
        JOURNAL.record("failed", job_id=job_id, queue=queue,
                       detail=(p.stderr.strip()[:300] or "renderer failed"))
        return jsonify(job_id=job_id, state="failed",
                       error=p.stderr.strip()[:300]), 500

    clipped = "clipped=True" in p.stdout
    JOURNAL.record(
        "sent", job_id=job_id, queue=queue,
        detail=("Renderer finished, but the page does not fit the printable area"
                if clipped else "Renderer finished, handed to the spooler"),
        geometry={"clipped": clipped, "scale_pinned": True},
    )
    return jsonify(
        job_id=job_id,
        state="sent",
        queue=queue,
        clipped=clipped,
        # Same word as everywhere else. The watcher will say what the spooler
        # did with it, and none of that proves a badge exists.
        note="sent to the spooler, which is not a promise that a badge exists",
    )


# ---------------------------------------------------------------------------
# The OnSite app's API. Versioned, because this one has a client that is not
# in this repository and cannot be changed in the same commit.
#
# Deliberately thin. The hub routes a job to a printer and says what happened
# to it. It does NOT describe media, page sizes or driver settings: choosing
# the right badge for the right printer is the app's business, and a hub that
# published its media assumptions would invite the app to trust them.
#
# Every printer is addressed by id, never by name. Names are for humans and
# they change; see printhub.identity.
# ---------------------------------------------------------------------------


def _printer_rows():
    """One row per enumerated queue, with its stable id attached."""
    config, _ = fleet.load(HUB_DIR)
    rows = []
    for q in faults.enumerate_queues():
        entry = config.get(q["queue"], {})
        rows.append({
            "printer_id": IDENTITY.printer_id(q["queue"]),
            "name": entry.get("label") or q["queue"],
            "queue": q["queue"],
            "driver": q["driver"],
            "offline": q["offline"],
            "dialog_port": q["dialog_port"],
        })
    return rows


@app.get("/api/v1/hub")
def api_hub():
    """Who this hub is, where it is, and what it can be asked.

    The endpoint list is here so the app discovers the API rather than
    hardcoding paths: a hub on an older build can advertise fewer of them
    without the app guessing.
    """
    addrs = identity_mod.addresses()
    primary = addrs[0] if addrs else None
    return jsonify(
        hub_id=IDENTITY.hub_id,
        name=socket.gethostname(),
        api_version=API_VERSION,
        # Link-local addresses are excluded: this box has one, it looks like
        # a real address and nothing can reach it (printhub.identity).
        address=primary,
        addresses=addrs,
        port=PORT,
        base_url=f"http://{primary}:{PORT}" if primary else None,
        endpoints={
            "hub": "/api/v1/hub",
            "printers": "/api/v1/printers",
            "print": "/api/v1/print",
            "job": "/api/v1/jobs/{job_id}",
        },
    )


@app.get("/api/v1/qr.png")
def api_qr():
    """The hub's base URL as a QR, so nobody types an address on an iPad.

    Encodes the URL only. Pairing (ENG-3781) will add a token to this, which
    is why it is generated per request rather than cached: the day it carries
    a credential, a stale image would be worse than a slow one.
    """
    import io
    import qrcode

    addrs = identity_mod.addresses()
    if not addrs:
        return jsonify(error="This hub has no routable address."), 503

    img = qrcode.make(f"http://{addrs[0]}:{PORT}")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), 200, {"Content-Type": "image/png",
                                 "Cache-Control": "no-store"}


@app.get("/api/v1/printers")
def api_printers():
    """Every printer this hub can route to.

    `accepting` is whether the hub would take a job for it right now. It is
    NOT a readiness claim: no printer on this bench reports a fault until a
    job is actually sent, so a printer that is accepting may still be out of
    ribbon, jammed or with its lid open. Render it as "can be sent to", never
    as a green light.
    """
    rows = []
    for row in _printer_rows():
        # Whatever is said here, /api/v1/print must agree: a printer listed
        # as accepting and then refused would be worse than either alone.
        reason = None
        if row["dialog_port"]:
            reason = "opens_dialog"
        elif row["offline"]:
            reason = "offline"
        rows.append({
            "printer_id": row["printer_id"],
            "name": row["name"],
            "queue": row["queue"],
            "accepting": reason is None,
            "reason": reason,
        })
    return jsonify(hub_id=IDENTITY.hub_id, printers=rows)


@app.post("/api/v1/print")
def api_print():
    """Send a PDF to one printer, by id.

    The client generates job_id and redelivery is normal, not exceptional
    (design rule 1). Reports "sent", never "printed": nothing in the print
    path can confirm a badge reached a tray (design rule 2).

    Renders in a child process. This route takes PDFs the hub did not
    author, and PDFium runs in-process, so a malformed file would otherwise
    take the whole agent down with it.
    """
    printer_id = (request.form.get("printer_id")
                  or request.args.get("printer_id") or "")
    job_id = (request.form.get("job_id") or request.args.get("job_id")
              or str(uuid.uuid4()))

    queue = IDENTITY.queue_for(printer_id)
    if not queue:
        return jsonify(state="refused", reason="unknown_printer",
                       error=f"No printer with id {printer_id!r} on this hub. "
                             f"Fetch /api/v1/printers for the current list."), 404

    prior = JOURNAL.seen(job_id)
    if prior:
        return jsonify(job_id=job_id, state=prior["state"], deduped=True,
                       printer_id=printer_id, first_seen=prior["first_seen"])

    if "pdf" not in request.files:
        return jsonify(state="refused", reason="no_pdf",
                       error="POST a PDF as the form field 'pdf'"), 400

    refusal = offline_refusal(queue)
    if refusal:
        JOURNAL.record("refused", job_id=job_id, queue=queue,
                       source=request.remote_addr,
                       detail=refusal[0].get_json()["error"])
        return refusal

    path = SPOOL_DIR / f"{job_id}.pdf"
    request.files["pdf"].save(path)

    config, _ = fleet.load(HUB_DIR)
    entry = config.get(queue, {})
    resolved, _problems = fleet.resolve(HUB_DIR, entry)
    blob = resolved.get("devmode")

    JOURNAL.record("accepted", job_id=job_id, queue=queue,
                   label=entry.get("label"), source=request.remote_addr,
                   detail=f"Accepted from the app for {printer_id}")

    cmd = [str(CHILD_PYTHON), "-m", "printhub.render", queue, str(path),
           "--name", f"hub {job_id}"]
    if blob:
        cmd += ["--devmode", blob]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=120, cwd=str(ROOT))
    except subprocess.TimeoutExpired:
        JOURNAL.record("failed", job_id=job_id, queue=queue,
                       detail="Renderer timed out after 120 s")
        return jsonify(job_id=job_id, state="failed",
                       error="renderer timed out"), 500

    if proc.returncode != 0:
        JOURNAL.record("failed", job_id=job_id, queue=queue,
                       detail=proc.stderr.strip()[:300] or "renderer failed")
        return jsonify(job_id=job_id, state="failed",
                       error=proc.stderr.strip()[:300]), 500

    clipped = "clipped=True" in proc.stdout
    JOURNAL.record("sent", job_id=job_id, queue=queue,
                   detail="Renderer finished, handed to the spooler",
                   geometry={"clipped": clipped, "scale_pinned": bool(blob)})

    return jsonify(
        job_id=job_id,
        state="sent",
        printer_id=printer_id,
        # True when the page did not fit the printable area. The hub prints
        # it anyway; the app is better placed to decide whether that matters.
        clipped=clipped,
        note="sent to the spooler, which is not a promise that a badge exists",
    )


@app.get("/api/v1/jobs/<job_id>")
def api_job(job_id):
    """What happened to one job.

    Poll this three to five seconds after sending. The ZC10L reports a fault
    about a second after the job arrives, so that window catches it, and the
    app can follow "we've sent your badge" with the actual cause without ever
    claiming a badge exists.
    """
    job = JOURNAL.seen(job_id)
    if not job:
        return jsonify(state="unknown", job_id=job_id,
                       error="No job with that id on this hub."), 404
    return jsonify(
        job_id=job_id,
        state=job["state"],
        printer=job.get("label") or job.get("queue"),
        detail=job.get("detail"),
        fault=job.get("fault"),
        first_seen=job.get("first_seen"),
        last_seen=job.get("last_seen"),
        events=[e["event"] for e in job.get("events", [])],
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
