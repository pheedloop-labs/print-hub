# PheedLoop Print Hub — spike working notes

Read this before you touch anything. It carries the decisions, the machine
facts, and the rules that are not obvious from the code.

## What this project is

A one-week engineering spike. The question: can a PheedLoop-built Windows
print agent replace the freeware AirPrint bridge that today sits between the
iPad OnSite app and the Zebra ZC10L card printer?

The spike produces **answers and a memo**, not product code. The rig in this
folder is throwaway. Do not grow it into the product. Do not add
abstractions, a plugin system, a database, or a web UI. If a change does not
help answer one of the eight memo questions, do not make it.

Full spike plan, including the eight questions and the day-by-day sequence:
https://claude.ai/code/artifact/a107db7a-78a7-4e59-8bc1-d917c5537ca4

## The machine

Windows 11, development workstation. User profile `pheed`. Project root
`C:\hub`.

| Thing | Value |
|---|---|
| Python | 3.12.10, machine scope. Launcher `py -3.12` |
| venv | `C:\hub\.venv` |
| venv python | `C:\hub\.venv\Scripts\python.exe` |
| Renderer | `C:\hub\SumatraPDF.exe` plus its DLLs, portable |
| Packages | flask, waitress, pywin32, pypdf, qrcode, reportlab |

`pywin32_postinstall.py -install` has been run as admin. If `import
win32print` fails, run it again from an admin shell.

## Print queues

| Queue | Port | Purpose |
|---|---|---|
| `HUB-CARD` | USB001 | the Zebra ZC10L. Driver `Zebra ZC10L USB Card Printer` |
| `HUB-PDF` | `C:\hub\out.pdf` | silent PDF target. Costs no media |
| `Microsoft Print to PDF` | `PORTPROMPT:` | never use. It opens a save dialog |

`HUB-PDF` is a second queue on the Microsoft PDF driver, bound to a file
port instead of `PORTPROMPT:`. A file port writes straight to disk and opens
no dialog. Use it for every test that does not need real media.

## The media

The ZC10L holds 5.5 x 3.5 inch badge stock. That is **139.7 x 88.9 mm**.

The spike artifact says 5.5 x 3.46 in. The artifact is wrong. Trust the
number here.

Every test page must be authored at the exact media size. A page authored at
the wrong size makes `noscale` meaningless: the renderer either clips a
fraction of a millimetre or the driver scales to fit, and neither failure is
visible by eye on a badge.

## Files

| File | Purpose |
|---|---|
| `hub.py` | the rig. Flask, five routes, one subprocess call |
| `caps.py` | dumps a driver's paper names, paperkind ids, and DEVMODE defaults |
| `make-test-card.py` | generates the calibration card. Takes width and height in mm |
| `test-card-139.7x88.9.pdf` | the current calibration card |
| `spool\` | saved job PDFs. Safe to delete |
| `out.pdf` | output of the `HUB-PDF` queue. Overwritten each print |

The calibration card carries a 1 mm ruler, a 100.00 mm horizontal caliper
target, a 50.00 mm vertical target, a line width ladder from 0.1 to 2.0 pt, a
text size ladder from 4 to 10 pt, and CMYK, RGB and grey patches.

## How the rig works

Configuration comes from environment variables. Never edit code to change a
printer.

| Variable | Meaning |
|---|---|
| `HUB_QUEUE` | print queue name. **Required.** The rig refuses to print without it |
| `HUB_MEDIA` | value for SumatraPDF `paper=`. Empty means the queue default |
| `HUB_COLOR` | `color` or `monochrome` |
| `HUB_SUMATRA` | path to `SumatraPDF.exe` |
| `HUB_DIR` | working directory. Default `C:\hub` |

Routes: `/health`, `/printers`, `/print` (POST a PDF as form field `pdf`),
`/jobs`, `/queue`.

Start it:

```
$env:HUB_SUMATRA = "C:\hub\SumatraPDF.exe"
$env:HUB_QUEUE   = "HUB-PDF"
C:\hub\.venv\Scripts\python.exe C:\hub\hub.py
```

The process reads every variable once at start. Restart it after any change.

## Design rules that must survive every edit

1. **The client generates `job_id`.** The agent keeps a dedupe log and
   refuses a repeat. Redelivery is normal, not exceptional.
2. **The agent reports `sent`, never `printed`.** The spooler reports that a
   job left the spooler, not that a card landed in the tray. Until spike 4
   proves a detectable completion signal exists, `printed` is a lie. An
   honest `sent` beats a false `printed`.
3. **`HUB_QUEUE` stays required.** A default queue is how a modal dialog gets
   into the print path, and a modal dialog blocks everything.
4. **Nothing lives under a user profile.** The shipped agent runs as
   LocalSystem with no interactive user. Use absolute machine-wide paths.
5. **Never trigger a dialog.** No `-print-dialog`, no message boxes, no
   `input()`. A dialog on a headless box is an outage.

## Verified so far

1. The ZC10L driver installs on Windows 11, despite Zebra's FAQ scoping it to
   Windows 7, 8.1 and 10. Queue type is `Local`, which a LocalSystem service
   needs.
2. The rig prints end to end against `HUB-PDF`: HTTP POST, spooled to disk,
   rendered by SumatraPDF, accepted by the driver.
3. SumatraPDF with `noscale` does not scale the page. Measured from the
   `HUB-PDF` output at 600 dpi: the 120 mm ruler read 120.100 mm, the 100 mm
   target 100.161 mm, the 50 mm target 50.165 mm. The error is constant at
   about 0.13 mm across all three lengths rather than proportional to length,
   which is antialiasing at the measurement threshold, not scaling.
4. Nothing was clipped. The ink bounding box measured 134.03 x 82.04 mm
   against 134 x 82 mm authored.
5. The Microsoft PDF driver rotated the landscape card 90° onto a portrait
   Letter page, and placed it at the page origin rather than centred.
   Orientation is a `DEVMODE` field.
6. The Microsoft PDF driver re-encodes the page as JPEG. Do not judge colour
   or text quality from `out.pdf`.

## Open task 1 — the card print fails

`HUB_QUEUE=HUB-CARD` with `HUB_MEDIA="140mm x 88mm"` returns SumatraPDF exit
code 1 and an empty stderr.

Two known causes, in order of likelihood:

1. The media string was wrong. 140 x 88 mm is not the stock size. The stock
   is 139.7 x 88.9 mm.
2. The driver may not accept a custom size at all, only its own named forms.

`-silent` suppresses the error dialog, which is why stderr is empty. To see
the real error, run the same command by hand without `-silent`.

Do this:

1. Run `C:\hub\.venv\Scripts\python.exe C:\hub\caps.py HUB-CARD`. Find the
   row near 139.7 x 88.9 mm. Record its exact name and its `paperkind` id.
2. Set `HUB_MEDIA` to that exact name. `paper=` accepts a printer-reported
   name as well as custom dimensions, and a named form avoids the question of
   custom size support entirely.
3. If no row is close, the driver needs a custom form defined. Report that
   rather than guessing.
4. Print the card. Then have a human measure the physical card with calipers
   and report both targets.

Do not burn more than one card per hypothesis. PVC costs real money. Test
every change against `HUB-PDF` first.

## Open task 2 — DEVMODE capture and replay (spike 2, gating)

The goal: store a fully configured driver settings blob and apply it to every
job, so a print from code matches a print configured by hand in the vendor
driver UI within 0.5 mm, with every vendor-specific option honoured.

Vendor-private driver settings live in the `dmDriverExtra` bytes after the
public `DEVMODE` structure. No portable API reaches them. `caps.py` prints
`DriverExtra`, which is the size of that blob in bytes. Above zero means this
task is real work.

Two constraints discovered already:

- **pywin32 exposes a `DEVMODE` object, not raw bytes.** Capture and replay
  needs a small `ctypes` layer over `DocumentProperties`: call it with mode 0
  to get the required buffer size, then with `DM_OUT_BUFFER` to fill a buffer
  of that size, then write the raw bytes to disk.
- **SumatraPDF cannot accept a DEVMODE blob.** It takes its own settings
  string only. So per-job DEVMODE does not compose with it.

The way around the second constraint, and the preferred design: write the
captured blob into the **queue's own default settings** with `SetPrinter`
level 2. Every renderer then inherits it, SumatraPDF included. That keeps
capture and replay as one problem instead of one problem per renderer.

`SetPrinter` needs administrator or manage-printer rights, and it changes the
queue globally. That is acceptable on a dedicated hub. Say so in the memo.

Acceptance for this task:

1. Configure the queue by hand in the vendor driver UI. Leave it correct.
2. Capture the blob to disk. Print from code.
3. Print the same PDF by hand from the driver dialog.
4. A human measures both cards with calipers. They must match within 0.5 mm.
5. Print once with the blob deliberately absent, so the team knows the
   failure signature on sight.

## Open task 3 — Session 0 service test (spike 1, gating)

Register the rig as a Windows service running as `LocalSystem` with `nssm`,
then print with nobody logged in.

```
nssm install PheedLoopHub "C:\hub\.venv\Scripts\waitress-serve.exe" ^
      "--listen=0.0.0.0:8080" "hub:app"
nssm set PheedLoopHub AppDirectory C:\hub
nssm set PheedLoopHub ObjectName LocalSystem
nssm start PheedLoopHub
```

`nssm` is not yet installed. Get it from nssm.cc and put `nssm.exe` on the
PATH.

Set the `HUB_*` variables machine-wide before you register the service. A
service does not inherit a shell's variables. Use
`[Environment]::SetEnvironmentVariable(name, value, "Machine")`.

Then hit `/printers` from the service and compare the list against the list
you get as `pheed`. A queue that appears for the user but not for LocalSystem
is a per-user queue, and that changes the process model.

The full no-login reboot test belongs on the mini PC, not this workstation.
Take the early signal here.

## Later tasks, in order

1. Bake off PDFium against SumatraPDF. SumatraPDF is GPLv3 and is a spike
   accelerator only. PDFium is BSD-licensed and is the safer thing to ship.
2. Spike 4. Break the printer on purpose — card jam, empty hopper, ribbon
   out — and record what the spooler reports and how long it takes. Produce a
   written list split in two: conditions the agent can detect, and conditions
   staff must catch by eye. That list is what the iPad is allowed to promise a
   registration desk.
3. Make the dedupe log durable on disk with a 24 hour window. It is in memory
   today.
4. Install a label printer driver (Brother QL-800 or DYMO 550) for cheap
   colour and text checks on paper instead of PVC.

## Explicitly out of scope this week

- The cloud transport and the WebSocket. All the risk sits in the Windows
  print path. Add the transport in week two when it is the only thing left.
- Reverse-engineering the Canon CX-G6400 wire format. A firmware update would
  own us. That printer is not on the desk yet anyway.
- The headless bootstrap ladder and the Wi-Fi hotspot rung. They need the
  mini PC.
- Any decision on C# against Python. That decision waits until the first
  three spikes finish, with maintainership as the tiebreaker.

## Environment gotchas

- In PowerShell, bare `curl` is an alias for `Invoke-WebRequest` and rejects
  `-F`. Use `curl.exe`.
- `Get-ChildItem -Filter` takes one pattern, not a list. Use `Where-Object`.
- `setx PATH` truncates PATH at 1024 characters. Never use it.
- PowerShell blocks `Activate.ps1` unless the execution policy allows local
  scripts. Prefer calling `C:\hub\.venv\Scripts\python.exe` by absolute path
  and never activating.
- `winget` fails with `0x8a15995e` when it reaches the `msstore` source. Pin
  `--source winget`.
- In reportlab, `setFillColorRGB` reads a fourth tuple value as alpha. An
  alpha of 0 makes every later object on the page invisible.

## Reporting

Every finding goes in the memo, including the negative ones. A driver that
refuses something is a finding. An error dialog's exact wording is a finding,
because customer IT will see the same dialog and the uncertified ZC10L driver
is a standing operational cost.

Ask a human to measure physical cards. You cannot hold calipers.