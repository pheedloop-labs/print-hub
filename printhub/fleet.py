"""Per-printer configuration, owned by this box.

The list of printers comes from Windows (faults.enumerate_queues). This file
holds only what Windows cannot tell us, keyed by queue name.

**Why a file still exists after printers.json was deleted.** Two things about
a printer are human decisions that no amount of enumeration will produce:

  * *Which captured DEVMODE blob to pin.* There are usually several per
    printer and they are not interchangeable — the Epson has a cut-on and a
    cut-off capture four bytes apart, and pinning the wrong one prints uncut
    badges forever while every reported number looks correct (Verified 43,
    47). Blob filenames do not match queue names and should not be forced to:
    the useful name says what the capture *is*.
  * *Which test card to send.* Page size is derivable from the driver, but
    the caliper targets are not. Defaulting them once silently re-authored
    the Epson card with a 50 mm vertical target in place of its 250 mm one.

This file is machine-local and gitignored, like the blobs it points at. A
fresh box has none, and that is correct: per-printer settings are captured on
the box, not delivered with the build. An unconfigured printer still appears
in the console, still reports its state, and is simply marked unconfigured.

Written by hand today. The console takes it over in ENG-3784, which is why
save() exists and why the shape is a flat dict keyed by queue name rather
than the old list-of-objects: a console edits one printer at a time.
"""

import json
import pathlib

CONFIG_NAME = "printers.local.json"


def path(hub_dir):
    return pathlib.Path(hub_dir) / CONFIG_NAME


def load(hub_dir):
    """Return {queue_name: {...}}, plus an error string or None.

    A missing file is not an error. A malformed one is, and it is reported
    rather than swallowed: silently behaving as though nothing is configured
    would mean printing unpinned, which is the failure this whole project
    keeps running into.
    """
    p = path(hub_dir)
    if not p.exists():
        return {}, None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, f"{type(exc).__name__}: {exc}"
    printers = data.get("printers", {})
    if not isinstance(printers, dict):
        return {}, f"{CONFIG_NAME}: 'printers' must be an object keyed by queue name"
    return printers, None


def save(hub_dir, printers):
    """Write the config back. Used by the console once ENG-3784 lands."""
    p = path(hub_dir)
    body = {
        "_comment": ("Per-printer configuration for this box, keyed by Windows "
                     "queue name. Machine-local: the blobs it points at are "
                     "queue- and machine-specific. See printhub/fleet.py."),
        "printers": printers,
    }
    p.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def resolve(hub_dir, entry):
    """Turn an entry's relative paths into absolute ones, and check they exist.

    Returns (resolved, problems). A configured path that does not exist is a
    problem worth surfacing: it is the difference between a pinned job and an
    unpinned one, and nothing downstream would notice.
    """
    root = pathlib.Path(hub_dir)
    resolved = dict(entry)
    problems = []
    for key in ("devmode", "card"):
        value = entry.get(key)
        if not value:
            continue
        full = root / value
        resolved[key] = str(full)
        if not full.exists():
            problems.append(f"{key} not found: {value}")
    return resolved, problems
