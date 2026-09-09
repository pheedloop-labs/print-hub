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

Windows 11. User profile `pheed`. Project root `C:\hub`. Hostname
`PHEEDLOOP-LABS`, reachable on Wi-Fi at 192.168.1.30.

**This box is the mini PC**, not a separate development workstation. Earlier
revisions of this file called it a workstation and deferred the no-login
reboot test to "the mini PC", which is this machine. There is nowhere else to
defer to, so that test belongs here.

Only Wi-Fi has a routable address; the Ethernet interface sits on a
169.254 link-local address, so there is no DHCP on it. The Wi-Fi profile
`PheedLoop Main` is an **All User Profile**, which is what makes the no-login
test possible: a per-user profile would leave the machine with no network
until somebody logged in.

| Thing | Value |
|---|---|
| Python | 3.12.10, machine scope. Launcher `py -3.12` |
| venv | `C:\hub\.venv` |
| venv python | `C:\hub\.venv\Scripts\python.exe` |
| Renderer | PDFium, via the `pypdfium2` wheel in the venv. No external exe |
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
| `devmode.py` | capture and replay a queue's DEVMODE, vendor bytes included |
| `devmode\` | captured blobs. Restore points, not source. Gitignored |
| `caps.py` | dumps a driver's paper names, paperkind ids, and DEVMODE defaults |
| `spike4_monitor.py` | polls a queue and logs every state change, with timing |
| `spike4-timeline.txt` | raw spike 4 timeline. Evidence for the memo |
| `make-test-card.py` | generates the calibration card. Edit `W, H` at the top |
| `test-card-140x88.pdf` | the current calibration card |
| `spool\` | saved job PDFs. Safe to delete. Gitignored |
| `out.pdf` | output of the `HUB-PDF` queue. Overwritten each print. Gitignored |

`make-test-card.py` takes no arguments, despite what earlier notes claimed.
The page size is the `W, H` constants at the top of the file.

The venv is gitignored, and so are any leftover SumatraPDF binaries still
sitting on the box: that renderer is GPLv3 and must never reach the repo.
PDFium arrives through the `pypdfium2` wheel in the venv, so there is no
renderer binary to manage any more. `.gitattributes` marks PDFs binary,
because git guesses "text" for reportlab's small output and would corrupt
the calibration card by converting its line endings.

The calibration card carries a 1 mm ruler, a 100.00 mm horizontal caliper
target, a 50.00 mm vertical target, a line width ladder from 0.1 to 2.0 pt, a
text size ladder from 4 to 10 pt, and CMYK, RGB and grey patches.

## How the rig works

Configuration comes from environment variables. Never edit code to change a
printer.

| Variable | Meaning |
|---|---|
| `HUB_QUEUE` | print queue name. **Required.** The rig refuses to print without it |
| `HUB_DIR` | working directory. Default `C:\hub` |

That is the entire configuration surface. Rendering takes no per-job
settings at all: the page is rendered at the device's own dpi and blitted
1:1, and the DC is built from the queue's own default DEVMODE, so driver
settings configured by hand are inherited. Colour and media are therefore
properties of the queue, not of the rig. Selecting `monochrome` per job
would mean editing DEVMODE, which is task 2 work.

Routes: `/health`, `/printers`, `/print` (POST a PDF as form field `pdf`),
`/jobs`, `/queue`.

Start it:

```
$env:HUB_QUEUE = "HUB-PDF"
C:\hub\.venv\Scripts\python.exe C:\hub\hub.py
```

Those two lines are all you need.

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
   rendered, accepted by the driver.
3. Historical, measured before the renderer was replaced, and kept only
   because it establishes the measurement floor on this box. From the
   `HUB-PDF` output at 600 dpi the 120 mm ruler read 120.100 mm, the 100 mm
   target 100.161 mm, the 50 mm target 50.165 mm. The error was constant at
   about 0.13 mm across all three lengths rather than proportional to length,
   which is antialiasing at the measurement threshold, not scaling. Treat
   roughly 0.1 mm as the noise floor for any measurement here.
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
11. **DEVMODE capture and replay works, vendor bytes included.**
    `devmode.py` captures all 6056 bytes of `HUB-CARD`'s default, 5836 of
    them driver-private, and writes them back byte-identically with
    `SetPrinter` level 2. Proven on both queues.

    Writes to the private region genuinely land. A byte-identical round trip
    alone would not prove that, since writing the same bytes back is
    indistinguishable from the write being ignored. Single-byte flips at
    private offsets 0, 4, 100 and 1000 all persisted, which settles it.
12. **A bad blob fails silently. This is the trap.** The ZC10L driver
    validates the private region as a whole. Zero all 5836 bytes and the
    driver discards the lot and substitutes its own, reporting success the
    whole way. So a botched replay looks exactly like a good one from the
    outside. Always read back and compare after applying; `devmode.py apply`
    does this and prints before, wanted and after hashes.

    This is also the answer to acceptance step 5. There is no visible
    failure signature to teach the team, because the driver self-heals
    rather than misprinting. Comfortable, but it hides mistakes, so the
    read-back is the safeguard rather than anything a human can spot.
13. The final private byte, offset 5835, is always rewritten by the driver.
    Do not expect byte-exact replay of a hand-edited blob. A genuine
    captured blob does round-trip exactly.
14. **`SetPrinter` level 2 does not need full administrator.** This shell is
    not elevated and the write still succeeds, so manage-printer rights are
    enough. That matters for the deployment model: the hub does not have to
    run elevated to own its queue settings.
15. Replay changes real rendering, not just stored bytes. Flipping
    `dmOrientation` on `HUB-PDF` moved the DC from 5100 x 6600 to
    6600 x 5100, and `pdfium_print.py` picked it up with no code change
    because it builds its DC with a NULL DEVMODE. Restoring the saved blob
    returned both the bytes and the geometry exactly.
16. The ZC10L reports exactly one form: paperkind **276**, named
    `140x88mm`, measuring 89.0 x 142.2 mm. Nothing near 139.7 x 88.9 mm
    exists. Custom forms are not a credible path: the driver claims a
    156.1 mm minimum length while its own only form is 142.2 mm long.
17. **Cross-config replay of the vendor bytes works, in both directions.**
    The operator set `Zoom-in/out[Z]` to 105 by hand. That moved exactly
    four driver-private bytes and nothing else of substance:

    | offset | 100% | 105% |
    |---|---|---|
    | private+644 | `0x64` = 100 | `0x69` = 105 |
    | private+668 | `0x00` | `0x01` |
    | private+672 | `0x64` = 100 | `0x00` |
    | private+684 | `0x1e` = 30 | `0x00` |

    Applying the 100% blob while the queue sat at 105% moved it to 100%, and
    applying 105% moved it back. This is the proof the task wanted: a
    vendor-only setting, reachable by no portable API, captured and replayed.

    Beware a red herring in that diff. Bytes 18 to 60 of the **public**
    section also differ, but they are residue after the NUL terminator inside
    the fixed 32-wchar `dmDeviceName` field, left from a longer string. Both
    blobs still name `HUB-CARD`. Do not read them as a settings change.
18. **A driver UI setting silently breaks the scale guarantee. Confirmed on
    PVC.** At 105% the driver reports `LOGPIXELSX` 315 instead of 300 and
    `HORZRES` 1764 instead of 1680, both exactly 1.05x, while `HORZSIZE`
    still claims the same 142 mm. Both claims cannot hold, and the card
    settled which one lies: **the printed card came out 5% oversized.**

    The reported dpi is dishonest. `pdfium_print` derives its scale from it,
    rendered 1737 px, and reported `raster_mm 140.063` in its own output.
    That number was a lie, and nothing anywhere raised an error. The rig
    would have answered `sent` with correct-looking geometry in its JSON
    while a 5% oversized card came off the printer.

    Treat "exact scale by construction" as conditional: it holds only when
    the DEVMODE in force is known. Pin it, per item 20.
19. **A `SetPrinter` write to the queue default does not stick on this
    driver.** It reverts within about ten seconds. The ZC10L re-asserts its
    own stored configuration, so anything written into the queue default is
    transient. The write succeeds, reads back correct, and then quietly goes
    away.

    That kills the design this file used to call preferred: capture the blob
    into the queue default and let every renderer inherit it. On this driver
    nothing can be made to stick that way.
20. **Per-job DEVMODE handed straight to `CreateDC` wins, and cannot be
    raced.** With the queue default sitting at zoom 105, a DC created with
    the zoom-100 blob reports 300 dpi and 1680 x 1051, while a NULL DEVMODE
    reports 315 and 1764 x 1103. So the fix is per-job, not per-queue:
    `pdfium_print --devmode <blob>`, or `HUB_DEVMODE` for the rig, which
    reports `scale_pinned` in `/health` and in every print response.

    Note what this means for the renderer decision. SumatraPDF could not
    accept a DEVMODE blob at all, which is exactly why the old notes reached
    for the queue-default design that this driver defeats. Dropping it is
    what makes this task solvable, not just a licensing convenience.
21. **The pin works end to end on media, against a hostile queue.** With the
    driver UI holding zoom 105, so that an unpinned job would have taken
    315 dpi and printed 5% oversized, a card posted through the rig with
    `HUB_DEVMODE` set used 300 dpi and measured **100.00 mm and 50.00 mm**
    on the two targets. The queue default was still 105 afterwards: the pin
    overrides, it does not repair the queue, which is the only approach that
    survives this driver's re-assertion.

    Keep the two cards together. The 105 card and this one came off the same
    PDF, so the only difference between them is the DEVMODE. That pair is
    the demonstration for the memo: a vendor UI setting can silently defeat
    scale, and a pinned blob defeats it back.
22. **A `LocalSystem` service prints.** Registered with `nssm` as
    `PheedLoopHub`, confirmed running as `LocalSystem` by
    `Win32_Service.StartName`, and it printed a card through HTTP with
    `scale_pinned: true` and 300 dpi. Session 0 is not an obstacle to the
    GDI print path.
23. **Machine-scope environment variables do reach the service.** `/health`
    from the service reported the right queue and the pinned blob, so
    `[Environment]::SetEnvironmentVariable(..., "Machine")` is a working
    delivery mechanism for `HUB_DEVMODE`. Worth stating because a service
    that starts without that variable prints silently wrong-sized cards.
24. **The printers are not per-user.** `HUB-CARD` is registered under
    `HKLM\SYSTEM\CurrentControlSet\Control\Print\Printers`, its
    `PER_USER` attribute is clear, and `HKCU\Printers\Connections` is empty.
    So the queue a logged-in user sees is the queue the service sees, which
    is what spike 1 needed and is confirmed by item 22 actually printing.
25. **A different computer on the network can drive the hub.** `curl` from
    another machine POSTed a PDF to `http://192.168.1.30:8080/print` and a
    card came out. Inbound 8080 needs an explicit firewall rule and a
    locally created one works. This is the transport half of the product
    proven with no cloud involved at all.
26. `/printers` answers `queue_visible: true` from the service itself, so the
    per-user question is settled by the service rather than by inference from
    the registry.
27. **The hub prints after a reboot with nobody logging in. Spike 1's gate
    is met.** Rebooted at 15:54:23, `curl` from another machine at 15:56:05,
    card produced. The operator authenticated nothing.

    The evidence, because "nobody logged in" deserves more than an
    assertion. The Winlogon operational log shows exactly one
    authentication, at 15:54:41, eighteen seconds after boot, which is
    Automatic Restart Sign-On rather than a person. `service.log` was created
    at 15:54:37, fourteen seconds after boot. The spool file
    `nologin-card-5.pdf` is stamped 15:56:05, and the first winlogon event
    consistent with a human unlocking the screen is 15:56:13, eight seconds
    *after* the print. No authentication occurred in between.

    Caveat worth carrying: ARSO means session 1 existed and the profile was
    loaded, so this is "no human logged in", not "no interactive session".
    That is the production condition, and item 24 independently rules out the
    per-user printer risk it could otherwise have masked.

28. **Repeatable across restarts, a reboot and a remote caller.** Every card
    printed through the pinned path came out the same: `pinned-card-1`,
    `service-card-1` and `nologin-card-1` through `5`, spanning a service
    reinstall, a `nssm restart`, a full reboot, and invocation from a
    different machine. The operator reports them all identical.

    The single card that differed was the deliberately unpinned one at zoom
    105, which is the point. Same PDF, same code path, same printer; the only
    variable that ever changed the output was the DEVMODE in force.

    Read this as consistency rather than precision. Two cards were measured
    with calipers at 100.00 and 50.00 mm; the rest were compared by eye
    against those. That is the right level of rigour for a repeatability
    check, but do not quote it as eight measured cards in the memo.

29. **Spike 4 answered: four faults detectable, but only reactively.** Out
    of cards, ribbon out, card jam and cover open all report distinct,
    correctly attributed statuses within about a second of a job arriving.
    Nothing reports anything while the queue is idle, including a jam with
    the printer's error light on, so there is no truthful pre-flight check
    and the agent can never promise "printer ready". A printer that is off
    or unplugged is the one fault with no proper signal at all: only WMI
    `WorkOffline`, after roughly 20 seconds, with no cause given. Full
    detail, timings and implementation traps in Closed task 4.

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

Still open here: `monochrome`, which needs DEVMODE work.

Worth a line in the memo regardless of which renderer ships. This
uncertified driver defeated a widely used renderer completely, and gave a
misleading error while doing it. Customer IT will meet the same driver.

Do not burn more than one card per hypothesis. PVC costs real money. Test
every change against `HUB-PDF` first.

## Closed task 2 — DEVMODE capture and replay (spike 2)

**Done, and the answer is stronger than the question.** Capture and replay of
the vendor-private bytes works, and it turned out to be mandatory rather than
merely nice: without it a setting in the driver UI silently changes printed
size. The gate is passed.

The goal was: store a fully configured driver settings blob and apply it to
every job, so a print from code matches a print configured by hand in the
vendor driver UI within 0.5 mm, with every vendor-specific option honoured.
Measured result: 0.00 mm apart on both targets, with the queue deliberately
left misconfigured to make the test mean something.

Vendor-private driver settings live in the `dmDriverExtra` bytes after the
public `DEVMODE` structure. No portable API reaches them. `caps.py` prints
`DriverExtra`, which is the size of that blob in bytes. Above zero means this
task is real work.

What is known already:

- **pywin32 exposes a `DEVMODE` object, not raw bytes.** Capture and replay
  needs a small `ctypes` layer over `DocumentProperties`: call it with mode 0
  to get the required buffer size, then with `DM_OUT_BUFFER` to fill a buffer
  of that size, then write the raw bytes to disk. `caps.py` and
  `pdfium_print.py` already do the reading half of this; the ZC10L reports
  6056 bytes total, 5836 of them driver-private.
- **With no blob given, the renderer inherits the queue default.**
  `pdfium_print.py` builds its DC with a NULL DEVMODE in that case, which
  looked like a convenience and is in fact the hazard: the queue default is
  exactly what a driver UI setting changes under you. Pass `--devmode`, or
  `HUB_DEVMODE` for the rig, and the blob wins instead.

**The design changed, because the old one does not work here.** Writing the
captured blob into the queue's own default with `SetPrinter` level 2 was the
plan, so every renderer would inherit it. On this driver the write reverts
within about ten seconds: the ZC10L re-asserts its own stored settings. See
Verified item 19.

What works is per-job: hand the blob straight to `CreateDC`. It overrides the
queue default and no background re-assertion can race it. `pdfium_print`
takes `--devmode`, and the rig takes `HUB_DEVMODE`. `SetPrinter` remains
useful only for capture-side experiments, not as the delivery mechanism.

`SetPrinter` changes the queue globally, which is acceptable on a dedicated
hub. Say so in the memo. It turned out **not** to need administrator, only
manage-printer rights, which is a better deployment story than assumed.

Acceptance for this task:

1. Configure the queue by hand in the vendor driver UI. Leave it correct.
   **Done**, in the sense that matters: the queue is in a state that prints
   correctly, verified by calipers, and the captured blob is that state.
2. Capture the blob to disk. Print from code. **Done.** `devmode.py capture`,
   then a card printed from code measuring 100.00 and 50.00 mm exactly.
3. Print the same PDF by hand from the driver dialog. **Done**, by the
   operator, before the renderer was replaced. Reported as correct.
4. A human measures both cards with calipers, matching within 0.5 mm.
   **Done**, both at 100.00 and 50.00 mm, so 0.00 mm apart. Note this step
   is weaker than it looks: a code print and a hand print both read the same
   queue default, so agreement is close to guaranteed and does not by itself
   prove the vendor bytes replayed. Items 11 to 13 in Verified are what
   actually prove that.
5. Print once with the blob deliberately absent, for the failure signature.
   **Done, and there is one after all**, though not the way this step
   imagined. Zeroing the vendor bytes produces nothing to look at: the
   driver rejects an invalid private region, silently substitutes its own
   and prints normally, so that route has no signature and cost no media to
   rule out. The real signature came from the zoom setting: with the driver
   UI at 105 and no blob pinned, the card prints **5% oversized** while
   every number the rig reports still looks right.

   That is the card to show the team. It is what a lost blob looks like, and
   it looks like nothing at all until you measure it.

**Task 2 is closed.** Cross-config replay is proven, using
`Zoom-in/out[Z]` at 100 and 105 as the two configurations (Verified 17). The
scale question is settled on PVC (Verified 18). The queue-default design was
found not to hold on this driver and was replaced with per-job DEVMODE
(Verified 19 and 20). The pin was then confirmed end to end against a
deliberately misconfigured queue: 100.00 and 50.00 mm (Verified 21).

Carry into the product: **the agent must pin a captured blob per job.**
Inheriting the queue default is not safe on this hardware, and the failure
is silent. `HUB_DEVMODE` does this today, and `/health` reports
`scale_pinned` so the condition is visible without printing anything.

Restore points live in `devmode\`, gitignored:

| file | contents |
|---|---|
| `HUB-CARD.restore.devmode` | zoom 100, the known-good config. Pin this one |
| `HUB-CARD.zoom105.devmode` | zoom 105, kept as the second config for replay tests |
| `HUB-PDF.restore.devmode` | the `HUB-PDF` default |

These are restore points on this box, not source, and they are gitignored.
A fresh machine needs its own captures: the vendor bytes are opaque and
`pdfium_print` refuses a blob taken from a different queue.

The queue is currently left at the zoom 100 blob. Put it back there after
any experiment, because 105% may misprint every card.

## Closed task 3 — Session 0 service test (spike 1)

**Passed.** The box was rebooted, nobody logged in, and a `curl` from another
machine on the network produced a card. Spike 1's gate is met.

| Thing | Status |
|---|---|
| `nssm.exe` | installed at `C:\hub\nssm.exe`, deliberately not on PATH |
| `PheedLoopHub` | RUNNING, `StartName` = `LocalSystem`, start = Auto |
| machine-scope `HUB_*` | reaches the service, `/health` confirms it |
| `/printers` from the service | `queue_visible: true` |
| printing as `LocalSystem` | works |
| printing from another machine | works, `curl` to `192.168.1.30:8080` |
| printing after reboot with no login | **works** |

The sequence that got here, for rebuilding on the next box:

```
[Environment]::SetEnvironmentVariable("HUB_QUEUE",   "HUB-CARD", "Machine")
[Environment]::SetEnvironmentVariable("HUB_DEVMODE", "C:\hub\devmode\HUB-CARD.restore.devmode", "Machine")
[Environment]::SetEnvironmentVariable("HUB_DIR",     "C:\hub", "Machine")

New-NetFirewallRule -DisplayName "PheedLoop Hub 8080" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Any

C:\hub\nssm.exe install PheedLoopHub "C:\hub\.venv\Scripts\waitress-serve.exe" "--listen=0.0.0.0:8080" "hub:app"
C:\hub\nssm.exe set PheedLoopHub AppDirectory C:\hub
C:\hub\nssm.exe set PheedLoopHub ObjectName LocalSystem
C:\hub\nssm.exe set PheedLoopHub Start SERVICE_AUTO_START
C:\hub\nssm.exe set PheedLoopHub AppStdout C:\hub\service.log
C:\hub\nssm.exe set PheedLoopHub AppStderr C:\hub\service.log
C:\hub\nssm.exe set PheedLoopHub AppRotateFiles 1
C:\hub\nssm.exe start PheedLoopHub
```

Order matters. Set the variables **before** starting the service, because it
reads them once. `HUB_DEVMODE` especially: a service that starts without it
inherits the queue default and prints silently wrong-sized cards, per
Verified 18. A code change needs `nssm restart`, not merely a new request.

### The one caveat, and why it does not sink the result

Nobody logged in, but the machine was not free of interactive sessions
either. Windows **Automatic Restart Sign-On** signed the account back in by
itself 18 seconds after boot and left the screen locked. So session 1
existed and the user profile was loaded, without any human authenticating.
See the ARSO note in the gotchas for how to read the evidence.

Two reasons to accept this as a pass rather than chase a stricter one:

1. **It is the production condition.** ARSO is on by default for this
   Microsoft account, so a real hub will always come back from a reboot with
   an auto-signed-in locked session. Testing that state is testing reality.
2. **The per-user risk it might have masked is independently excluded.**
   Verified 24: `HUB-CARD` lives in `HKLM`, its `PER_USER` attribute is
   clear, and `HKCU\Printers\Connections` is empty. There is no per-user
   printer here to hide behind a loaded profile.

If a stricter answer is ever wanted, the way to get it is to set
`DisableAutomaticRestartSignOn` to 1 under
`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System`, reboot, and
confirm `quser` reports no session at all before printing. One card. Worth
doing only if the shipped design stops relying on ARSO, or if the account
model changes to one where ARSO does not apply.

### Still not tested

The security posture. The service auto-starts and listens on all interfaces
with **no authentication**, so anything that can reach port 8080 can print a
card. Acceptable in the lab; not acceptable on a venue network. Out of scope
this week along with the transport, but it must not ship this way.

## Closed task 4 — what the spooler reports when the printer breaks (spike 4)

**Done.** Four faults induced deliberately on real hardware, with
`spike4_monitor.py` polling three independent sources twice a second. The raw
timeline is in `spike4-timeline.txt`.

Two findings dominate, and neither was on the list of things this task set
out to learn.

### The queue is only truthful while a job is in flight

Every consumable fault reported `Status 0x0`, WMI `Idle`, and `Get-Printer`
**`Normal`** until a badge was actually sent. A card jam with the printer's
own error light lit read as a perfectly healthy queue. Send one job and the
correct fault appears in under a second.

So **the agent cannot pre-flight the printer.** It can never truthfully tell
an iPad "printer ready". It can only say "the badge you just sent failed,
because X". No green light, only red ones, and only after somebody has
already tried to print. That bounds the product promise more than anything
else in this spike.

### The agent cannot confirm a card exists

A job clears the queue identically whether or not media emerged, in about
two seconds either way. Nothing distinguishes a good badge from a mangled,
blank or double-fed one. The rig also returned
`{"state":"sent","dpi":300,"raster_mm":[140.039,88.053],"scale_pinned":true}`
for a printer that was **physically unplugged**, correct geometry and all.

Design rule 2 is now evidence rather than caution. `sent` is the only honest
word available.

### What the agent CAN detect and name

Only while a job is in flight, except door open. Latency is from the POST
arriving, measured against the spool file's mtime.

| Condition | Spooler `Status` | WMI `DetectedErrorState` | Latency |
|---|---|---|---|
| Out of cards | `PAPER_OUT` `0x00000010` | `NoPaper` (4) | 0.7 s |
| Ribbon out | `NO_TONER` `0x00040000` | `NoToner` (6) | 1.0 s |
| Card jam | `PAPER_JAM` `0x00000008` | `Jammed` (8) | 0.9 s |
| Cover open | `DOOR_OPEN` `0x00400000` | `DoorOpen` (7) | immediate, and visible while idle |

Four distinct, correctly attributed causes. The iPad can name the actual
problem to a desk rather than shrugging, which is a genuinely useful promise
even though it is reactive.

### What staff must catch by eye

- **Printer powered off or unplugged.** The spooler `Status` field never
  changes, not once, through disconnect, stuck job, reconnect and printing.
  `PRINTER_STATUS_OFFLINE` exists in the API and is never set. The only
  signal is WMI `WorkOffline` flipping true after about 20 seconds, and it
  never says why. `Get-Printer` reports `Normal` throughout.
- **Any fault at all while the queue is idle.** See above. An idle poll is
  worthless.
- **A badge that printed wrongly.** No signal exists, at all.
- **Whether a card physically landed in the tray.**

### Operational timings worth knowing

- Recovery is automatic. The queued job prints itself once the fault clears;
  nobody needs to resubmit.
- Recovery latency splits in two. A hopper refill that does not open the main
  cover completes in **1.4 s**. Anything that opens the main cover, so a jam
  clear or a ribbon change, takes **34 to 40 s**, because the printer
  re-initialises. **Do not raise an alarm in the first minute after a
  cover-open fix**, or the agent will cry wolf on every ribbon change.
- A job survived a printer being unplugged for over two minutes and printed
  **2.3 s** after reconnect.
- The whole print lifecycle is visible for roughly **1.4 s**. Poll slower
  than about a second and the job's existence is missed entirely.

### Traps for whoever implements this

- **Job status lies. Poll printer status, not job status.** A job reads
  `PRINTING|RETAINED` (`0x2010`) while the printer is jammed, empty or out of
  ribbon. `pStatus` is always empty. Anything reading job state concludes the
  badge is coming out right now.
- **One condition at a time.** `PAPER_OUT` was *replaced* by `DOOR_OPEN`,
  not OR-ed with it. Fixing the reported fault can simply reveal the next
  one, so the agent cannot describe a compound failure.
- **The event log is empty.** `PrintService/Admin` is enabled by default and
  recorded **zero** events across every fault here.
  `PrintService/Operational` is **disabled** by default and enabling it needs
  elevation: `wevtutil sl "Microsoft-Windows-PrintService/Operational"
  /e:true`. Do not plan on event-log-driven detection without turning it on
  first and confirming it says anything useful.
- **WMI `DetectedErrorState` is an activity artifact, not a health field.**
  It reads `NoError` only while actively printing and reverts to `Unknown`
  at idle, so `Unknown` does not mean healthy.
- `/queue` already surfaces the printer `Status` integer, so the rig needs no
  change to expose all of this. `status: 16` is out of cards, `8` jammed,
  `262144` no ribbon, `4194304` cover open.

## Later tasks, in order

1. Move rendering into a child process. PDFium runs in-process today, so a
   malformed PDF that crashes it takes the whole agent down. The renderer
   choice itself is settled, so this is the last piece of it outstanding.
   The bake-off is closed: the alternative could not print a card at all,
   and the GPLv3 dependency is retired.
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
- Same trap in `EnumPrinters`: **level 4 returns dicts too**, so
  `p[2]` raises `KeyError: 2`. Use `p["pPrinterName"]`. This sat unnoticed in
  `/printers` until the Session 0 test called that route for the first time.
  Assume any pywin32 call returning a structure gives you a dict here.
- `nssm set <svc> ObjectName LocalSystem` prints "Reset parameter ObjectName
  to its default", which looks like a failure and is not: LocalSystem is
  nssm's default. Confirm the truth with
  `Get-CimInstance Win32_Service -Filter "Name='PheedLoopHub'"` and read
  `StartName`, rather than trusting nssm's wording.
- Always set `AppStdout` and `AppStderr` on an nssm service. Session 0 has no
  console, so without a log a startup crash or a route raising an exception
  is completely invisible. The `/printers` bug above was diagnosed purely
  from `service.log`.
- `nssm.exe` lives at `C:\hub\nssm.exe` and is called by absolute path on
  purpose. It is deliberately **not** on the PATH, because `setx PATH`
  truncates at 1024 characters and there is no reason to risk it.
- **"Nobody logged in" needs proof, and Windows makes it confusing.**
  Automatic Restart Sign-On signs the account back in by itself after a
  reboot, roughly 18 seconds in, and leaves the screen locked. The operator
  sees a lock screen and correctly says they never logged in, while `quser`
  reports an Active session with a logon time in the same minute as the boot.
  Both are true. To tell what actually happened, read
  `Microsoft-Windows-Winlogon/Operational` for "Authentication started" and
  compare its timestamp against the spool file's mtime in `spool\`, which is
  when the POST arrived. One automatic authentication seconds after boot, and
  no other before the print, means no human was involved. `quser` alone will
  mislead you, and `AutoAdminLogon` being `0` does not rule ARSO out: it is
  governed by `DisableAutomaticRestartSignOn` instead.
- Set `argtypes` before calling GDI through `ctypes`. An `HDC` overflows the
  default `int` marshalling and raises "int too long to convert".
- PDFium's default bitmap format is BGR, whose stride is not 4-byte aligned.
  GDI DIBs require aligned rows, so force `FPDFBitmap_BGRx`.
- Do not name a scratch script after a stdlib module. An `enum.py` beside
  the script shadowed `enum` and broke `win32timezone` deep inside pywin32.
- File visibility is inconsistent under the agent sandbox. The leftover
  SumatraPDF binaries were listed by one call and reported absent by the
  next, and git and Python could not see them at all even while the exe was
  running fine. Never conclude a file is missing from a single failed check.

## Reporting

Every finding goes in the memo, including the negative ones. A driver that
refuses something is a finding. An error dialog's exact wording is a finding,
because customer IT will see the same dialog and the uncertified ZC10L driver
is a standing operational cost.

Ask a human to measure physical cards. You cannot hold calipers.