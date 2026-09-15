# print-hub

A one-week engineering spike: can a purpose-built Windows print agent replace
a freeware AirPrint bridge between an iPad app and an event badge printer?

**This is a spike record, not software you should run.** The rig here exists
to answer questions and produce a memo. It listens on all interfaces with no
authentication, keeps its dedupe log in memory, and renders PDFs in-process.
Every one of those is a deliberate shortcut, documented as such, and none of
them belongs anywhere near a venue network. Read it for the findings.

## What was actually measured

Five printers, four vendors' driver models, 203 to 600 dpi, on one Windows 11
box through one code path:

| printer | dpi | media |
|---|---|---|
| Zebra ZC10L | 300 | 140 x 88 mm PVC card |
| Brother QL-800 | 300 | 62 mm continuous DK tape |
| EPSON CW-C4000u | 600 | 102 x 302 mm folded badge stock |
| Zebra ZD621 | 203 | 88 x 76 mm mark-sensed label |
| DYMO LabelWriter 550 Turbo | 300 | 30252 address label |

One conclusion organises the rest. **Everything about getting bytes onto media
generalised. Nothing about knowing what happened did.** All five printed
correct geometry with no conditionals in the renderer. But the three whose
faults were induced on real hardware put the answer in three *different* API
fields, and two printers from the same vendor behaved so differently that no
shared promise survives.

Some of the specifics, all reproducible from the notes:

- A vendor UI setting can make a driver **report 315 dpi while printing at
  300**, so the card comes out 5% oversized while every number the software
  reports looks correct.
- Another driver **reports itself monochrome and prints red**. A driver's
  self-description is evidence, not truth.
- Public `dmScale` is inert on every driver tested. Real settings live in the
  `dmDriverExtra` bytes, 320 to 30320 of them, reachable by no portable API.
  A captured blob carries them, and turns out to double as a configuration
  backup that survives a printer being removed and re-added.
- No printer can be truthfully described as **"ready"**, and none can confirm a
  badge physically exists. The software returned success, with geometry correct
  to 0.01 mm, for a printer that was unplugged.
- On one printer, the obvious recovery, "detect the paused job and resume it",
  is **a badge shredder that reports success**.

## Where to read

- **[CLAUDE.MD](CLAUDE.MD)** is the real document: the working ledger, every
  verified finding with its evidence, the traps, and the negative results.
  Written for whoever picks this up next, including the mistakes.
- **`docs/printer-benchmark.html`** compares the five printers field by field, and
  carries the reproducible procedure for adding a sixth. Untested is marked as
  untested throughout rather than inferred.
- **`docs/onsite-api.md`** is the API contract for the OnSite app.
- **`docs/spike-memo.html`** is the decision memo, written in Simplified Technical
  English.

## The tools

| file | purpose |
|---|---|
| `hub.ps1` | task runner: install, start/stop/restart, status, demo, capture |
| `hub.py` | entry point. The service runs `waitress-serve hub:app` |
| `printhub/app.py` | Flask rig. `/health`, `/printers`, `/print`, `/demo`, `/jobs`, `/queue` |
| `printhub/render.py` | the renderer: PDFium raster, GDI blit, exact scale by construction |
| `printhub/devmode.py` | capture and replay a queue's DEVMODE, vendor-private bytes included |
| `printhub/faults.py` | enumerate the queues, and read one honest state each from three disagreeing sources |
| `printhub/fleet.py` | per-printer config for this box: which blob to pin, which card to send |
| `printhub/identity.py` | stable ids for the hub and its printers, and which address to advertise |
| `printhub/journal.py` | the job record: per-day JSONL, durable dedupe, and never the word printed |
| `printhub/watcher.py` | polls every queue at 0.5 s, the only thing fast enough to see a job |
| `console/` | the hub console: Svelte + Vite, PheedLoop design tokens |
| `tools/benchmark.py` | one objective row per queue, including the exact page size to author at |
| `tools/caps.py` | a driver's paper forms, paperkind ids and resolved defaults |
| `tools/make_test_card.py` | caliper-measurable calibration cards at any page size |
| `tools/spike4_monitor.py` | poll a queue and log every state change, with timing |
| `cards/` | one calibration card per printer, authored to its imageable area |
| `docs/` | the bench record, the decision memo, the raw fault timelines |

Windows only, and specific to these five printers. `pywin32`, `pypdfium2`,
`reportlab`, `flask`, `waitress`.

## On the vendors

The findings name products and are sometimes unflattering. They are
observations from one box with one firmware revision at one point in time, not
a verdict on any company's engineering. Several of the sharpest results are
about *Windows print API* gaps that no vendor controls. Where a driver was the
cause, the evidence is in the notes and the method is reproducible.

Vendor driver installers and captured DEVMODE blobs are deliberately not in
this repository: the installers are redistributable binaries that are not ours
to ship, and the blobs are machine- and queue-specific restore points that
would be useless anywhere else.
