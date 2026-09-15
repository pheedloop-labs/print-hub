"""Read what a print queue is actually doing, from all three sources.

No single source is sufficient, and no two agree about where the truth
lives. Measured on three printers broken deliberately (CLAUDE.MD Verified
50):

    printer          printer Status   job Status        job pStatus
    Zebra ZC10L      named, 4 codes   lies: PRINTING    empty
    Brother QL-800   generic ERROR    flags PAUSED|ERR  empty
    DYMO 550         generic ERROR    ERROR, not paused a sentence

So this module reads the printer status bitfield, the job status bitfield
and the pStatus string, and reports what each one said. Reading pStatus is
nearly free and on the DYMO it is the difference between "it failed" and
"wrong labels".

Two rules this module exists to enforce, both of them findings:

  * **Never report ready.** No fault is visible while the queue is idle -
    a card jam with the printer's own error light lit reads as a perfectly
    healthy queue until a job is sent (Verified 29). `idle` here means "no
    fault reported", which is not the same thing and must not be rendered
    as a green light.
  * **A job with zero status bits is the offline signature** (Verified 55),
    and it is distinct from the PAUSED|ERROR of a real fault. A detector
    keyed on JOB_STATUS_PAUSED alone misses both the DYMO and this.

**Offline needs a fourth source, and it is not optional.** The spooler never
sets PRINTER_STATUS_OFFLINE on any printer tested, `Get-Printer` reports
Normal, and `DetectedErrorState` reads 0. WMI `WorkOffline` is the only
signal that exists (Verified 55). Skipping it was tried, on the grounds that
a bitless queued job approximates it; that approximation is worth nothing
while the queue is empty, and the console cheerfully reported "No fault
reported" for two printers that were switched off. One WMI query covers the
whole fleet, so it costs one round trip per poll rather than one per printer.

Two caveats it carries. WorkOffline takes about 20 seconds to flip after a
device disappears, and it never says why. And Windows' own "Use Printer
Offline" setting sets the same flag, so the honest wording is "reported
offline", not "unplugged".
"""

import threading
import time

import win32print

# Printer status bits that name a fault. PAPER_OUT was *replaced* by
# DOOR_OPEN rather than OR-ed with it, so a printer reports one condition at
# a time and a compound failure cannot be described (Verified, Closed task 4).
PRINTER_BITS = [
    (0x00000001, "PAUSED",       "Queue is paused"),
    (0x00000002, "ERROR",        "Error, cause not reported by this driver"),
    (0x00000008, "PAPER_JAM",    "Card or label jammed"),
    (0x00000010, "PAPER_OUT",    "Out of cards or labels"),
    (0x00000080, "OFFLINE",      "Reported offline"),
    (0x00000400, "OUT_OF_MEMORY", "Out of memory"),
    (0x00000800, "DOOR_OPEN",    "Cover open"),
    (0x00040000, "NO_TONER",     "Ribbon or toner out"),
    (0x00400000, "DOOR_OPEN",    "Cover open"),
]

# Job status bits. The Brother puts its fault here and nowhere else.
JOB_BITS = [
    (0x00000001, "PAUSED"),
    (0x00000002, "ERROR"),
    (0x00000004, "DELETING"),
    (0x00000010, "PRINTING"),
    (0x00000020, "OFFLINE"),
    (0x00000040, "PAPEROUT"),
    (0x00000080, "PRINTED"),
    (0x00000100, "DELETED"),
    (0x00000200, "BLOCKED_DEVQ"),
    (0x00000400, "USER_INTERVENTION"),
    (0x00000800, "RESTART"),
    (0x00001000, "COMPLETE"),
    (0x00002000, "RETAINED"),
]

JOB_FAULT_BITS = 0x00000002 | 0x00000020 | 0x00000040 | 0x00000400  # ERROR OFFLINE PAPEROUT USER_INTERVENTION


def _decode(value, table):
    return [name for bit, name, *_ in table if value & bit]


_com_ready = threading.local()
_offline_lock = threading.Lock()
_offline_cache = {"at": -1e9, "value": None}

# WMI costs about 1.1 s on this box, which is half a poll interval, and
# WorkOffline takes roughly 20 s to flip anyway. Caching for a few seconds
# therefore adds nothing measurable to a signal that is already slow, and
# takes the cost off almost every request.
OFFLINE_TTL = 5.0


def _ensure_com():
    """CoInitialize once per thread, and never uninitialize.

    The hub is served by waitress on worker threads and COM raises
    "CoInitialize has not been called" on any thread that has not done so.
    Uninitializing after each query was tried and is wrong: it tears COM down
    while the result objects are still alive, which prints "Win32 exception
    occurred releasing IUnknown" to the service log. Worker threads are
    long-lived, so initialize once and leave it.
    """
    if getattr(_com_ready, "done", False):
        return
    import pythoncom
    pythoncom.CoInitialize()
    _com_ready.done = True


def _query_offline():
    try:
        import win32com.client
        _ensure_com()
        wmi = win32com.client.GetObject("winmgmts:")
        rows = wmi.ExecQuery("SELECT Name, WorkOffline FROM Win32_Printer")
        return {row.Name for row in rows if row.WorkOffline}
    except Exception:
        return None


def offline_queues(max_age=OFFLINE_TTL):
    """Queue names WMI reports as offline, or None if WMI could not be asked.

    One query for every printer, not one per printer: five round trips per
    poll would be the expensive version of this.

    None and an empty set mean different things and must not be collapsed.
    Empty means WMI answered and nothing is offline; None means the question
    could not be put, so the caller must not claim a printer is online.
    """
    now = time.monotonic()
    with _offline_lock:
        if now - _offline_cache["at"] < max_age:
            return _offline_cache["value"]
        value = _query_offline()
        _offline_cache["at"] = now
        _offline_cache["value"] = value
        return value


def read(queue, offline=None):
    """Return one honest reading for a queue. Opens and closes a handle.

    offline is this queue's WMI WorkOffline flag, or None when WMI could not
    be asked. Pass it from offline_queues() so one query serves the fleet.
    """
    out = {
        "queue": queue,
        "state": "unknown",
        "reachable": False,
        "status": None,
        "printer_faults": [],
        "job_faults": [],
        "pstatus": None,
        "jobs_queued": 0,
        "offline": offline,
        "detail": None,
        "driver": None,
        "port": None,
        "error": None,
    }

    try:
        handle = win32print.OpenPrinter(queue)
    except Exception as exc:
        out["state"] = "unreachable"
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out

    try:
        info = win32print.GetPrinter(handle, 2)
        jobs = win32print.EnumJobs(handle, 0, 25, 1)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    finally:
        win32print.ClosePrinter(handle)

    out["reachable"] = True
    out["driver"] = info.get("pDriverName")
    out["port"] = info.get("pPortName")
    status = info.get("Status", 0) or 0
    out["status"] = status
    out["jobs_queued"] = len(jobs)

    seen = []
    for bit, name, text in PRINTER_BITS:
        if status & bit and name not in seen:
            seen.append(name)
            out["printer_faults"].append({"code": name, "text": text})

    # Source two and three: the job. The Brother's fault is only here, and
    # the DYMO writes a whole sentence into pStatus.
    job_status = 0
    bitless_job = False
    for job in jobs:
        js = job.get("Status", 0) or 0
        job_status |= js
        if js == 0:
            bitless_job = True
        ptext = (job.get("pStatus") or "").strip()
        if ptext and not out["pstatus"]:
            out["pstatus"] = ptext
    out["job_faults"] = _decode(job_status, [(b, n) for b, n in JOB_BITS])

    # Decide a state. Order matters: the most specific evidence wins, and
    # "no fault reported" is never upgraded to "ready".
    if offline:
        # First, because a printer that is not there explains everything else
        # about it, and every other source will insist it is healthy.
        out["state"] = "offline"
        out["detail"] = ("Windows reports this printer offline. It is usually "
                         "switched off or unplugged, though the Use Printer "
                         "Offline setting sets the same flag. Nothing else "
                         "reports this, and it takes about 20 seconds to appear.")
    elif out["printer_faults"]:
        out["state"] = "fault"
        out["detail"] = out["pstatus"] or out["printer_faults"][0]["text"]
    elif out["pstatus"]:
        # The DYMO reports "Unknown label detected" here while its printer
        # status says only ERROR. Trust the sentence over the bitfield.
        out["state"] = "fault"
        out["detail"] = out["pstatus"]
    elif job_status & JOB_FAULT_BITS:
        out["state"] = "fault"
        out["detail"] = "The job reports an error the printer status did not name"
    elif jobs and bitless_job:
        # Verified 55: queued, no bits, not progressing. The printer was on a
        # different USB port and every other source read healthy.
        out["state"] = "stalled"
        out["detail"] = ("A job is queued reporting no status at all. On this "
                         "bench that meant the printer was not connected.")
    elif jobs:
        out["state"] = "printing"
        out["detail"] = f"{len(jobs)} job(s) in the queue"
    else:
        # NOT ready. No fault is detectable while the queue is idle.
        out["state"] = "idle"
        if offline is None:
            out["detail"] = ("No fault reported, and WMI could not be asked "
                             "whether this printer is offline - which is the "
                             "only source that would say so.")
        else:
            out["detail"] = ("No fault reported. A fault only becomes visible "
                             "once a job is sent.")

    return out
