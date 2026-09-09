"""Watch a print queue and record every state change, with timing.

Spike 4. Break the printer on purpose and find out what Windows actually
reports, and how long it takes to say it. The output of this is the two
column list the memo needs: conditions the agent can detect, and conditions
staff must catch by eye.

Three independent sources, because they do not agree and the disagreement is
itself a finding:

  * spooler printer status  - GetPrinter level 2 Status bitfield
  * spooler job status      - EnumJobs level 2 Status bitfield and pStatus
  * WMI Win32_Printer       - PrinterStatus, DetectedErrorState

Prints a line only when something changes, so a quiet queue stays quiet and
the timeline stays readable.

    spike4_monitor.py [queue] [--interval 0.5]
"""

import argparse
import datetime
import sys
import time

import win32print

PRINTER_STATUS = {
    0x00000001: "PAUSED", 0x00000002: "ERROR",
    0x00000004: "PENDING_DELETION", 0x00000008: "PAPER_JAM",
    0x00000010: "PAPER_OUT", 0x00000020: "MANUAL_FEED",
    0x00000040: "PAPER_PROBLEM", 0x00000080: "OFFLINE",
    0x00000100: "IO_ACTIVE", 0x00000200: "BUSY",
    0x00000400: "PRINTING", 0x00000800: "OUTPUT_BIN_FULL",
    0x00001000: "NOT_AVAILABLE", 0x00002000: "WAITING",
    0x00004000: "PROCESSING", 0x00008000: "INITIALIZING",
    0x00010000: "WARMING_UP", 0x00020000: "TONER_LOW",
    0x00040000: "NO_TONER", 0x00080000: "PAGE_PUNT",
    0x00100000: "USER_INTERVENTION", 0x00200000: "OUT_OF_MEMORY",
    0x00400000: "DOOR_OPEN", 0x00800000: "SERVER_UNKNOWN",
    0x01000000: "POWER_SAVE",
}

JOB_STATUS = {
    0x00000001: "PAUSED", 0x00000002: "ERROR", 0x00000004: "DELETING",
    0x00000008: "SPOOLING", 0x00000010: "PRINTING", 0x00000020: "OFFLINE",
    0x00000040: "PAPEROUT", 0x00000080: "PRINTED", 0x00000100: "DELETED",
    0x00000200: "BLOCKED_DEVQ", 0x00000400: "USER_INTERVENTION",
    0x00000800: "RESTART", 0x00001000: "COMPLETE", 0x00002000: "RETAINED",
    0x00004000: "RENDERING_LOCALLY",
}

WMI_PRINTER_STATUS = {
    1: "Other", 2: "Unknown", 3: "Idle", 4: "Printing", 5: "WarmingUp",
    6: "StoppedPrinting", 7: "Offline",
}

WMI_ERROR_STATE = {
    0: "Unknown", 1: "Other", 2: "NoError", 3: "LowPaper", 4: "NoPaper",
    5: "LowToner", 6: "NoToner", 7: "DoorOpen", 8: "Jammed",
    9: "ServiceRequested", 10: "OutputBinFull", 11: "PaperProblem",
    12: "CannotPrintPage", 13: "UserInterventionRequired",
    14: "OutOfMemory", 15: "ServerUnknown",
}


def bits(value, table):
    if value == 0:
        return "(none)"
    names = [n for b, n in sorted(table.items()) if value & b]
    unknown = value & ~sum(b for b in table if value & b)
    if unknown:
        names.append(f"unknown:0x{unknown:x}")
    return "|".join(names) or f"0x{value:x}"


def printer_state(queue):
    h = win32print.OpenPrinter(queue)
    try:
        info = win32print.GetPrinter(h, 2)
        try:
            jobs = win32print.EnumJobs(h, 0, 99, 2)
        except Exception:
            jobs = win32print.EnumJobs(h, 0, 99, 1)
    finally:
        win32print.ClosePrinter(h)
    return info, jobs


def wmi_state(queue):
    try:
        import win32com.client
        wmi = win32com.client.GetObject("winmgmts:")
        q = ("SELECT PrinterStatus, DetectedErrorState, "
             "ExtendedDetectedErrorState, WorkOffline "
             f"FROM Win32_Printer WHERE Name = '{queue}'")
        for p in wmi.ExecQuery(q):
            return {
                "PrinterStatus": p.PrinterStatus,
                "DetectedErrorState": p.DetectedErrorState,
                "ExtendedDetectedErrorState": p.ExtendedDetectedErrorState,
                "WorkOffline": p.WorkOffline,
            }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {}


def snapshot(queue):
    info, jobs = printer_state(queue)
    w = wmi_state(queue)
    job_lines = []
    for j in jobs:
        job_lines.append(
            f"job {j.get('JobId')} "
            f"status={bits(j.get('Status', 0), JOB_STATUS)} "
            f"pStatus={(j.get('pStatus') or '')!r} "
            f"pages={j.get('PagesPrinted')}/{j.get('TotalPages')}")
    return {
        "printer_status": info.get("Status", 0),
        "printer_status_text": bits(info.get("Status", 0), PRINTER_STATUS),
        "cJobs": info.get("cJobs"),
        "wmi_status": WMI_PRINTER_STATUS.get(w.get("PrinterStatus"),
                                            w.get("PrinterStatus")),
        "wmi_error": WMI_ERROR_STATE.get(w.get("DetectedErrorState"),
                                         w.get("DetectedErrorState")),
        "wmi_ext_error": w.get("ExtendedDetectedErrorState"),
        "wmi_offline": w.get("WorkOffline"),
        "jobs": job_lines,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("queue", nargs="?", default="HUB-CARD")
    ap.add_argument("--interval", type=float, default=0.5)
    a = ap.parse_args()

    start = time.time()
    print(f"# watching {a.queue} every {a.interval}s. Ctrl-C to stop.")
    print(f"# started {datetime.datetime.now().isoformat(timespec='seconds')}")
    print("# only changes are printed. elapsed seconds in brackets.")
    print(flush=True)

    last = None
    while True:
        try:
            now = snapshot(a.queue)
        except Exception as exc:
            now = {"fatal": f"{type(exc).__name__}: {exc}"}

        if now != last:
            stamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            elapsed = time.time() - start
            print(f"[{elapsed:8.2f}s] {stamp}")
            if "fatal" in now:
                print(f"    QUERY FAILED: {now['fatal']}")
            else:
                print(f"    printer : 0x{now['printer_status']:08x}  "
                      f"{now['printer_status_text']}")
                print(f"    wmi     : status={now['wmi_status']} "
                      f"error={now['wmi_error']} "
                      f"ext={now['wmi_ext_error']} "
                      f"offline={now['wmi_offline']}")
                print(f"    queued  : {now['cJobs']}")
                for line in now["jobs"]:
                    print(f"    {line}")
            print(flush=True)
            last = now

        time.sleep(a.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n# stopped")
        sys.exit(0)
