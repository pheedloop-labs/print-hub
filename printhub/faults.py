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

Offline detection is deliberately incomplete. The spooler never sets
PRINTER_STATUS_OFFLINE, on any printer tested; the only true signal is WMI
WorkOffline, which takes about 20 seconds and never says why. That costs a
WMI round trip per poll, so it is not done here. `stalled` is the cheap
approximation and it is honest about being one.
"""

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


def read(queue):
    """Return one honest reading for a queue. Opens and closes a handle."""
    out = {
        "queue": queue,
        "state": "unknown",
        "reachable": False,
        "status": None,
        "printer_faults": [],
        "job_faults": [],
        "pstatus": None,
        "jobs_queued": 0,
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
    if out["printer_faults"]:
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
        out["detail"] = "No fault reported. A fault only becomes visible once a job is sent."

    return out
