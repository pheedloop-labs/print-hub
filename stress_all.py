"""Print to every printer at once, and record what the spooler does about it.

The closest thing in this rig to a real event: several badge stations feeding
different printers in the same second. Nothing else in the spike has tested
concurrency, and the interesting questions are not whether it works.

  * Does the spooler serialise the jobs or run them in parallel?
  * Does the slowest printer delay the others? The Epson page is 17.2
    megapixels and the DYMO's is 0.29, a 60x spread.
  * Does one printer's fault block another's queue?
  * Is there GDI or spooler contention that shows up only under load?

Each printer gets its own correctly sized card and its own pinned blob,
because a page authored for the wrong device is meaningless (CLAUDE.md, the
media sections). One process per printer, so PDFium state is not shared:
this tests the Windows print path under concurrency, not the rig's
threading, which is single-queue by design.

    stress_all.py            print on every configured printer
    stress_all.py --dry-run  render and measure, spool nothing, cost no media
"""

import subprocess
import sys
import threading
import time

import win32print

PY = r"C:\hub\.venv\Scripts\python.exe"
PRINTER = r"C:\hub\pdfium_print.py"

# queue, card, pinned blob
PAIRS = [
    ("HUB-CARD",
     r"C:\hub\test-card-140x88.pdf",
     r"C:\hub\devmode\HUB-CARD.restore.devmode"),
    ("Brother QL-800",
     r"C:\hub\test-card-83.98x58.92.pdf",
     r"C:\hub\devmode\QL800.62mm-blackred.devmode"),
    ("EPSON CW-C4000u (Copy 1)",
     r"C:\hub\test-card-101.97x301.99.pdf",
     r"C:\hub\devmode\C4000u.102x302-autocut.devmode"),
    ("ZDesigner ZD621-203dpi ZPL",
     r"C:\hub\test-card-87.96x76.19.pdf",
     r"C:\hub\devmode\ZD621.88x76-mark-cut.devmode"),
    ("DYMO LabelWriter 550 Turbo",
     r"C:\hub\test-card-25.31x81.53.pdf",
     r"C:\hub\devmode\DYMO550.30252-address.devmode"),
]

PRINTER_STATUS = {
    0x00000001: "PAUSED", 0x00000002: "ERROR", 0x00000008: "PAPER_JAM",
    0x00000010: "PAPER_OUT", 0x00000080: "OFFLINE", 0x00000200: "BUSY",
    0x00000400: "PRINTING", 0x00002000: "WAITING", 0x00004000: "PROCESSING",
    0x00040000: "NO_TONER", 0x00100000: "USER_INTERVENTION",
    0x00400000: "DOOR_OPEN",
}
JOB_STATUS = {0x1: "PAUSED", 0x2: "ERROR", 0x8: "SPOOLING", 0x10: "PRINTING",
              0x80: "PRINTED", 0x1000: "COMPLETE", 0x2000: "RETAINED"}

dry = "--dry-run" in sys.argv
t0 = time.perf_counter()
events = []
lock = threading.Lock()
stop = threading.Event()


def bits(v, table):
    return "|".join(n for b, n in sorted(table.items()) if v & b) or "-"


def watch():
    """Poll every queue and record only changes, with elapsed time."""
    last = {}
    while not stop.is_set():
        for queue, _, _ in PAIRS:
            try:
                h = win32print.OpenPrinter(queue)
                try:
                    info = win32print.GetPrinter(h, 2)
                    jobs = win32print.EnumJobs(h, 0, 99, 2)
                finally:
                    win32print.ClosePrinter(h)
            except Exception:
                continue
            snap = (info.get("Status", 0), info.get("cJobs", 0),
                    tuple((j.get("Status", 0), j.get("pStatus") or "")
                          for j in jobs))
            if last.get(queue) != snap:
                with lock:
                    events.append((time.perf_counter() - t0, queue, snap))
                last[queue] = snap
        time.sleep(0.25)


results = {}


def run(queue, card, blob):
    cmd = [PY, PRINTER, queue, card, "--devmode", blob, "--name",
           f"stress-{queue.split()[0].lower()}"]
    if dry:
        cmd.append("--dry-run")
    launched = time.perf_counter() - t0
    p = subprocess.run(cmd, capture_output=True, text=True)
    done = time.perf_counter() - t0
    with lock:
        results[queue] = (launched, done, p.returncode, p.stdout, p.stderr)


print(f"{'DRY RUN, nothing spooled' if dry else 'LIVE, this spends media'}")
print(f"launching {len(PAIRS)} prints as simultaneously as the OS allows\n")

monitor = threading.Thread(target=watch, daemon=True)
monitor.start()

threads = [threading.Thread(target=run, args=p) for p in PAIRS]
for t in threads:
    t.start()
for t in threads:
    t.join()

time.sleep(6)          # let the spooler drain and settle
stop.set()
monitor.join(timeout=3)

print(f"{'queue':<28} {'launch':>7} {'exit':>7} {'took':>7}  rc  geometry")
print("-" * 96)
for queue, _, _ in PAIRS:
    launched, done, rc, out, err = results[queue]
    geo = next((l.strip() for l in out.splitlines() if "raster" in l), "")
    print(f"{queue:<28} {launched:7.3f} {done:7.3f} {done - launched:7.3f} "
          f"{rc:3}  {geo[:44]}")
    if rc != 0:
        print(f"    STDERR: {err.strip()[:200]}")

skew = max(r[0] for r in results.values()) - min(r[0] for r in results.values())
wall = max(r[1] for r in results.values())
print(f"\nlaunch skew {skew * 1000:.0f} ms   total wall clock {wall:.3f} s"
      f"   sum of individual times {sum(r[1] - r[0] for r in results.values()):.3f} s")

print(f"\nspooler timeline, {len(events)} state changes")
print("-" * 96)
for el, queue, (pst, njobs, jobs) in events:
    jd = " ".join(f"[{bits(js, JOB_STATUS)}{' ' + repr(ps) if ps else ''}]"
                  for js, ps in jobs)
    print(f"  {el:6.2f}s  {queue:<28} printer={bits(pst, PRINTER_STATUS):<12}"
          f" jobs={njobs} {jd}")
