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
| Packages | flask, waitress, pywin32, pypdf, qrcode, reportlab, pypdfium2 |

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

The stock is **3.5 inch wide by 5.5 inch high**, portrait. That is
88.9 x 139.7 mm. The operator confirmed the orientation by hand.

Author every test page at **140.0 x 88.0 mm landscape**. That is what
actually prints correctly. Verified with calipers on a physical card: the
100.00 mm target read 100.00 mm and the 50.00 mm target read 50.00 mm.

Earlier revisions of this file said the media was 139.7 x 88.9 mm and put
the long axis first, then told you to trust that over the spike artifact.
Both the number and the axis order were wrong. Do not "correct"
`make-test-card.py` back to 139.7 x 88.9.

The driver reports one form, named `140x88mm`, and the name understates it:
it measures 89.0 x 142.2 mm portrait. The queue's DEVMODE sets
`Orientation = 2`, landscape, which yields a 142.24 x 88.98 mm imaging area
at 300 dpi. The long axis carries roughly 2.5 mm of overbleed past the
139.7 mm card, which is why a 140 mm page fits with nothing clipped.

Every test page must still be authored at its exact intended size. A page
authored at the wrong size makes `noscale` meaningless: the renderer either
clips a fraction of a millimetre or the driver scales to fit, and neither
failure is visible by eye on a badge.

## Files

| File | Purpose |
|---|---|
| `hub.py` | the rig. Flask, five routes |
| `pdfium_print.py` | the renderer. PDFium raster, GDI blit, exact scale |
| `caps.py` | dumps a driver's paper names, paperkind ids, and DEVMODE defaults |
| `make-test-card.py` | generates the calibration card. Edit `W, H` at the top |
| `test-card-140x88.pdf` | the current calibration card |
| `spool\` | saved job PDFs. Safe to delete. Gitignored |
| `out.pdf` | output of the `HUB-PDF` queue. Overwritten each print. Gitignored |

`make-test-card.py` takes no arguments, despite what earlier notes claimed.
The page size is the `W, H` constants at the top of the file.

The SumatraPDF binaries and the venv are gitignored. SumatraPDF is GPLv3 and
must not end up in the repo; PDFium arrives through the `pypdfium2` wheel in
the venv. `.gitattributes` marks PDFs binary, because git guesses "text" for
reportlab's small output and would corrupt the calibration card by
converting its line endings.

The calibration card carries a 1 mm ruler, a 100.00 mm horizontal caliper
target, a 50.00 mm vertical target, a line width ladder from 0.1 to 2.0 pt, a
text size ladder from 4 to 10 pt, and CMYK, RGB and grey patches.

## How the rig works

Configuration comes from environment variables. Never edit code to change a
printer.

| Variable | Meaning |
|---|---|
| `HUB_QUEUE` | print queue name. **Required.** The rig refuses to print without it |
| `HUB_RENDERER` | `pdfium` or `sumatra`. Default `pdfium` |
| `HUB_MEDIA` | value for SumatraPDF `paper=`. Empty means the queue default |
| `HUB_COLOR` | `color` or `monochrome` |
| `HUB_SUMATRA` | path to `SumatraPDF.exe` |
| `HUB_DIR` | working directory. Default `C:\hub` |

`HUB_MEDIA` and `HUB_COLOR` apply to the SumatraPDF path only. The PDFium
path inherits the queue's own default DEVMODE, so there is nothing to pass
per job. Honouring `monochrome` there means editing DEVMODE, which is task 2
work. `HUB_SUMATRA` matters only for the bake-off.

Keep `sumatra` selectable for the bake-off. Do not use it for cards: it
cannot open the `HUB-CARD` queue at all. See below.

Routes: `/health`, `/printers`, `/print` (POST a PDF as form field `pdf`),
`/jobs`, `/queue`.

Start it:

```
$env:HUB_QUEUE = "HUB-PDF"
C:\hub\.venv\Scripts\python.exe C:\hub\hub.py
```

`HUB_RENDERER` defaults to `pdfium`, so that is all you need. Set
`HUB_SUMATRA` only when running the bake-off.

The process reads every variable once at start. Restart it after any change.
Check `/health` and confirm `renderer` and `queue` read what you expect: a
stale instance still holding port 8080 will answer for the one you just
started, and it answers with the old code.

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
   `input()`. A dialog on a headless box is an outage. Running a renderer by
   hand without `-silent` to read its error dialog is fine at a console, and
   is how task 1 was diagnosed, but it must never be in the rig's own path.

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
7. **PDFium prints to the ZC10L, and SumatraPDF cannot.** A card printed
   from `pdfium_print.py` directly, and a second printed end to end over
   HTTP through the rig. The spool payload was 65812 bytes both ways, byte
   for byte, so the HTTP path adds nothing of its own.
8. Scale is correct on real PVC. Calipers on a physical card read the
   100.00 mm target at 100.00 mm and the 50.00 mm target at 50.00 mm.
9. Measured on `HUB-PDF`, the PDFium path reproduced the source PDF's ink
   bounding box width exactly, 134.112 mm against 134.112 mm, with the
   height one 600 dpi pixel over at 82.127 against 82.084. It placed the
   page centred and unrotated, which is strictly better than item 5.
10. The whole Win32 print path to `HUB-CARD` is healthy: `OpenPrinter`,
    `DocumentProperties` (6056 bytes, 5836 of them driver-private) and
    `CreateDC` all succeed, and a direct GDI job prints. Any renderer that
    fails on this queue is failing on its own account.
11. The ZC10L reports exactly one form: paperkind **276**, named
    `140x88mm`, measuring 89.0 x 142.2 mm. Nothing near 139.7 x 88.9 mm
    exists. Custom forms are not a credible path: the driver claims a
    156.1 mm minimum length while its own only form is 142.2 mm long.

## Closed task 1 — the card print failed because of the renderer

Resolved. Neither of the two hypotheses this file used to list was right. It
was not the media string, and it was not missing custom-size support.

**SumatraPDF 3.6.1 cannot open the `HUB-CARD` queue at all.** It fails with
exit code 1 and this dialog, which `-silent` was suppressing:

```
Printing problem.
Printer with given name doesn't exist
```

A deliberately nonexistent printer name produces the *identical* dialog, so
that wording is generic and does not mean what it says. The queue plainly
exists.

The failure is unconditional. Tested against a paused queue, so no media was
spent: every `-print-settings` value fails, including `paper=140x88mm` with
the driver's exact form name and bare `noscale` with no `paper=` at all, and
so does every flag combination down to `-print-to HUB-CARD file.pdf` with no
settings whatsoever. No job ever reaches the spooler. A failure that
precedes any paper negotiation cannot be a media-string failure.

Ruled out, each one a finding in its own right:

- 32/64-bit mismatch. Every binary is x64.
- `SumatraPDF-settings.txt`. A pristine `-appdata` directory fails the same.
- Printer enumeration. `HUB-CARD` appears at every level and flag `HUB-PDF`
  does.
- Queue configuration. Both queues are `winprint` with datatype `RAW`.
- Printer name form. Exact, lowercase, UNC, dot-host and trailing-space all
  return 1.
- `-print-to-default` is separately broken: it reports success while
  printing nothing, on both queues. Never trust its exit code.

The fix was the renderer, not a configuration value. `pdfium_print.py`
renders at the device's own dpi and blits 1:1 with `StretchDIBits`, so
`noscale` is structural rather than something asked of a renderer, and it
takes its DC from the queue's default DEVMODE so hand-configured driver
settings are inherited. This is the same inheritance that task 2 wants.

One cost to carry into the product: PDFium runs **in-process**. A PDF that
crashes it now takes down the agent, where SumatraPDF's subprocess gave that
isolation for free. The shipped agent should render in a child process.

Still open here: `monochrome` on the PDFium path, which needs DEVMODE work,
and whether SumatraPDF fails on every third-party driver or only Zebra's.
Installing the label printer from the later-tasks list answers the second
one, and customer IT will hit whichever answer it is.

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

1. Finish the PDFium/SumatraPDF bake-off. Mostly settled already, and not on
   licensing: SumatraPDF cannot print a card at all, so PDFium is the
   default and the GPLv3 dependency is retired. What is left is a quality
   comparison on the queues where both work, and the child-process
   rendering question above.
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
- **When testing a card print, pause the queue, and purge before you
  resume.** Pausing lets a job spool and hold, so you can see whether the
  renderer reached the spooler without feeding PVC. Resuming while a job is
  still queued prints it. This cost a card: a cleanup block resumed first
  and purged second, and the purge never ran because the process died in
  between. Purge, verify the queue is empty, then resume, and refuse to
  resume if anything is still queued.
- `git` is not on the PowerShell `PATH` on this box. Use the bash tool, or
  call `git.exe` by absolute path.
- Pausing a queue is `SetPrinter` with `PRINTER_CONTROL_PAUSE`. There is no
  `Suspend-Printer` cmdlet; `Suspend-PrintJob` pauses a job, not the queue.
- The spooler registers a job a moment after the renderer exits, and a file
  port writes `out.pdf` later still. Check for a job or a file in a wait
  loop, never immediately. Two apparent failures in this work were this race
  and nothing else.
- In this pywin32 build `DeviceCapabilities` returns dicts, not tuples:
  `DC_PAPERSIZE` gives `{'x','y'}` and `DC_MINEXTENT`/`DC_MAXEXTENT` give
  `{'Width','Length'}`, all in tenths of a millimetre.
- Set `argtypes` before calling GDI through `ctypes`. An `HDC` overflows the
  default `int` marshalling and raises "int too long to convert".
- PDFium's default bitmap format is BGR, whose stride is not 4-byte aligned.
  GDI DIBs require aligned rows, so force `FPDFBitmap_BGRx`.
- Do not name a scratch script after a stdlib module. An `enum.py` beside
  the script shadowed `enum` and broke `win32timezone` deep inside pywin32.
- File visibility is inconsistent under the agent sandbox. The SumatraPDF
  binaries were listed by one call and reported absent by the next, and git
  and Python cannot see them at all even though the exe runs. `sumatra_found`
  in `/health` is therefore not evidence of anything.

## Reporting

Every finding goes in the memo, including the negative ones. A driver that
refuses something is a finding. An error dialog's exact wording is a finding,
because customer IT will see the same dialog and the uncertified ZC10L driver
is a standing operational cost.

Ask a human to measure physical cards. You cannot hold calipers.