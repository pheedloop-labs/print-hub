"""The job record: what the hub was asked to print, and what happened next.

**Why this exists rather than reading the queue.** The whole print lifecycle
is visible in the spooler for roughly 1.4 seconds (CLAUDE.MD, Closed task 4).
Anything polling slower than about a second misses that a job existed at all,
so the live queue is not a record and a browser cannot reconstruct one. The
hub watches at 0.5 s and writes here; everything else reads this.

Append-only JSONL, one file per day under `journal/`. Daily files mean the
24 hour dedupe window is "today plus yesterday" and there is no compaction
step to get wrong. Events are never rewritten, only added, so a crash halfway
through a day costs at most the last line.

**Events, not statuses.** A job accumulates events - accepted, spooled,
fault, cleared - and the console rolls them up. Storing one mutable row per
job would mean deciding, at write time, which observation was the "real"
outcome, and that is exactly the judgement the hub is not entitled to make.

**`cleared` is not `printed`.** A job leaves the queue in about two seconds
whether or not media emerged, and nothing distinguishes a good badge from a
blank or double-fed one (design rule 2, Verified 29). The word printed does
not appear in this module.
"""

import datetime
import json
import pathlib
import threading

RETAIN_DAYS = 2          # today and yesterday: covers the 24 h dedupe window
MAX_ROLLUP = 200         # jobs kept in memory for the console

# How far a job has got. Ranked, not sequential, because the two writers race:
# the request thread records `sent` when the renderer returns, while the
# watcher may already have seen the job in the queue and recorded `spooled`.
#
# `accepted` and `sent` are written synchronously and always happen.
# `spooled` and `cleared` are the watcher's observations and are best-effort:
# a ZD621 label was confirmed printed having passed through the spooler
# between two 0.5 s ticks, so a job that never reaches `spooled` has not
# necessarily failed. `fault` and `failed` outrank all of these.
PROGRESS = {"accepted": 0, "sent": 1, "spooled": 2, "cleared": 3}


def _today():
    return datetime.datetime.now().strftime("%Y-%m-%d")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


class Journal:
    def __init__(self, hub_dir):
        self.dir = pathlib.Path(hub_dir) / "journal"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # job_id -> rolled up job. Ordered by first sight, oldest first.
        self._jobs = {}
        self._load()

    # --- persistence ------------------------------------------------------

    def _file(self, day=None):
        return self.dir / f"{day or _today()}.jsonl"

    def _recent_files(self):
        today = datetime.date.today()
        days = [today - datetime.timedelta(days=n) for n in range(RETAIN_DAYS)]
        return [self._file(d.strftime("%Y-%m-%d")) for d in days]

    def _load(self):
        """Rebuild the rollup from disk so a restart does not lose the record.

        Reads oldest file first so replay order matches write order. A
        corrupt line is skipped rather than fatal: a half-written last line
        after a power cut must not stop the hub starting.
        """
        for path in reversed(self._recent_files()):
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    self._apply(json.loads(line))
                except (ValueError, KeyError):
                    continue

    def _apply(self, event):
        """Fold one event into the rollup. Used by both replay and live writes."""
        job_id = event.get("job_id")
        if not job_id:
            return
        job = self._jobs.get(job_id)
        if job is None:
            job = {
                "job_id": job_id,
                "queue": event.get("queue"),
                "label": event.get("label"),
                "source": event.get("source"),
                "first_seen": event.get("at"),
                "last_seen": event.get("at"),
                "state": "accepted",
                "events": [],
                "fault": None,
                "detail": None,
            }
            self._jobs[job_id] = job
            # Trim oldest. dicts keep insertion order, so this is FIFO.
            while len(self._jobs) > MAX_ROLLUP:
                self._jobs.pop(next(iter(self._jobs)))

        job["last_seen"] = event.get("at", job["last_seen"])
        for key in ("queue", "label", "source"):
            if event.get(key) and not job.get(key):
                job[key] = event[key]

        kind = event.get("event")
        job["events"].append({"event": kind, "at": event.get("at"),
                              "detail": event.get("detail")})

        # State is the most significant thing observed, not the most recent.
        # A job that faulted and then cleared still faulted, and events can
        # arrive out of order: the watcher may see a job in the queue before
        # the renderer has returned, so progress is ranked rather than
        # assigned by whichever event landed last.
        if kind in ("failed", "fault"):
            job["state"] = kind if kind == "failed" else "fault"
            if kind == "fault":
                job["fault"] = event.get("detail")
        elif job["state"] not in ("fault", "failed"):
            rank = PROGRESS.get(kind)
            if rank is not None and rank > PROGRESS.get(job["state"], -1):
                job["state"] = kind

        if event.get("detail"):
            job["detail"] = event["detail"]
        if event.get("geometry"):
            job["geometry"] = event["geometry"]

    def record(self, event, **fields):
        """Append one event and fold it in. Safe from any thread."""
        row = {"event": event, "at": _now()}
        row.update({k: v for k, v in fields.items() if v is not None})
        line = json.dumps(row, default=str)
        with self._lock:
            try:
                with open(self._file(), "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                # A record we cannot persist is still worth having in memory
                # for the console, and must not fail the print it describes.
                pass
            self._apply(row)

    # --- reading ----------------------------------------------------------

    def seen(self, job_id):
        """Dedupe. Durable across a restart, unlike the old in-memory dict."""
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def recent(self, limit=50):
        """Newest first, for the console."""
        with self._lock:
            jobs = list(self._jobs.values())
        return [dict(j) for j in reversed(jobs[-limit:])]

    def count(self):
        with self._lock:
            return len(self._jobs)
