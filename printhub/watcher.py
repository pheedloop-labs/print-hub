"""Watch every queue twice a second and write what happens to the journal.

**This is the only thing in the hub that polls fast enough to see a job.**
The whole print lifecycle is visible for roughly 1.4 seconds and a fault
appears about a second after the job arrives (CLAUDE.MD, Closed task 4), so
anything slower misses both. The console polls every 2 s and reads this
watcher's last snapshot rather than the spooler, which means one poller feeds
everything and the console cannot miss a job the hub saw.

What it records, and the words it is allowed to use:

    spooled   the spooler has the job
    fault     a fault was observed while the job was in flight, with cause
              where the driver names one
    cleared   the job left the queue

`cleared` is not `printed`. A job leaves in about two seconds whether or not
media emerged, and the rig once reported perfect geometry for a printer that
was physically unplugged. Nothing here may imply a badge exists.

Faults are attributed to the job in flight because that is the only time they
are visible at all: an idle queue reports nothing, including a jam with the
printer's own error light lit.
"""

import threading
import time

from . import faults

INTERVAL = 0.5
DOC_PREFIX = "hub "


class Watcher:
    def __init__(self, journal, interval=INTERVAL):
        self.journal = journal
        self.interval = interval
        self._lock = threading.Lock()
        self._snapshot = {"printers": [], "at": None}
        # (queue, spooler job id) -> {job_id, faulted}
        self._live = {}
        self._thread = None
        self._stop = threading.Event()

    # --- lifecycle --------------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        # Daemon: the watcher must never hold the service open on shutdown.
        self._thread = threading.Thread(target=self._run, name="watcher",
                                        daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                # A watcher that dies silently would take the whole job record
                # with it, and nothing would say so. Keep going.
                pass
            self._stop.wait(self.interval)

    # --- reading ----------------------------------------------------------

    def snapshot(self):
        """The last reading, or None before the first tick."""
        with self._lock:
            if self._snapshot["at"] is None:
                return None
            return dict(self._snapshot)

    # --- the poll ---------------------------------------------------------

    def _tick(self):
        readings = []
        seen_keys = set()

        for q in faults.enumerate_queues():
            reading = faults.read(q["queue"], offline=q["offline"])
            reading.update(
                dialog_port=q["dialog_port"],
                duplicate_port=q["duplicate_port"],
                shared=q["shared"],
                network=q["network"],
            )
            readings.append(reading)
            for key in self._observe(q["queue"], reading):
                seen_keys.add(key)

        # Anything we were tracking and did not see this tick has left.
        for key in [k for k in self._live if k not in seen_keys]:
            tracked = self._live.pop(key)
            self.journal.record(
                "cleared",
                job_id=tracked["job_id"],
                queue=key[0],
                detail="Left the spooler. This does not mean a badge exists.",
            )

        with self._lock:
            self._snapshot = {"printers": readings, "at": time.time()}

    def _observe(self, queue, reading):
        """Record what this queue's in-flight jobs are doing. Returns keys seen."""
        keys = []
        for job in reading.get("jobs", []):
            key = (queue, job["id"])
            keys.append(key)
            tracked = self._live.get(key)

            if tracked is None:
                job_id = self._job_id(queue, job)
                tracked = {"job_id": job_id, "faulted": False}
                self._live[key] = tracked
                self.journal.record(
                    "spooled", job_id=job_id, queue=queue,
                    detail=f"Spooler accepted {job.get('document') or 'a job'}",
                )

            # A fault is recorded once per job, not once per tick, or a
            # cover left open would write two entries a second.
            if reading["state"] == "fault" and not tracked["faulted"]:
                tracked["faulted"] = True
                self.journal.record(
                    "fault", job_id=tracked["job_id"], queue=queue,
                    detail=reading.get("detail") or "Fault reported, cause not named",
                )
        return keys

    @staticmethod
    def _job_id(queue, job):
        """Link a spooler job back to the job_id the client generated.

        print_pdf names the document "hub <job_id>", so ours are recoverable.
        Anything else on these queues is somebody printing from the desktop;
        it is still recorded, under a synthetic id, because "what did this hub
        print" should not quietly omit it.
        """
        doc = (job.get("document") or "").strip()
        if doc.startswith(DOC_PREFIX):
            return doc[len(DOC_PREFIX):].strip()
        return f"external:{queue}:{job['id']}"
