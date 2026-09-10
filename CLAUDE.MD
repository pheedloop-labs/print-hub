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

Read that as scheduling, not as a product decision. The web interface in
particular is **deferred, not rejected**: the operator considers it fully
relevant and likely necessary in the finished product. It is banned here
because building it this week would answer no memo question and would cost
attention the Windows print path needs. See the out-of-scope list for the
job it will do.

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
| `Brother QL-800` | USB003 | DK label roll, 62 mm continuous. Cheap paper tests |
| `EPSON CW-C4000u (Copy 1)` | USB002 | the working Epson. 102 x 302 mm badge stock, black mark |
| `EPSON CW-C4000u` | USB002 | **orphan.** Enumerable but invisible in Windows. Do not use |
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

## The Brother QL-800 media

Different enough from the card printer to be worth its own note. The
operator selected form `62mm`, paperkind **259**, and set the paper type to
black/red by hand.

| Thing | Value |
|---|---|
| form | `62mm`, paperkind 259, 62.0 x 89.8 mm |
| tape | 62 mm wide, continuous. No fixed length |
| physical page | 1062 x 732 px at 300 dpi |
| **imageable** | **992 x 696 px = 83.99 x 58.93 mm**, landscape |
| offset | 35, 18 px = 2.96 mm left, 1.52 mm top |

**Author Brother pages at 83.98 x 58.92 mm**, not at 83.99 x 58.93. PDFium
rounds its raster up, so the exact imageable size rasters to 993 x 697 into
a 992 x 696 area and `pdfium_print` correctly reports `clipped=True`. A hair
under lands exactly on 992 x 696 with `clipped=False` and a scale error of
0.009 mm. The overhang is only 0.084 mm, below this box's noise floor, but
it is the difference between a guarantee and a coincidence.

Author against the **imageable** size on any driver, never the form size.
The ZC10L and the Epson report zero offset with physical equal to imageable,
so the distinction never came up before the Brother.

**Red prints, and the driver denies it can.** See Verified 37. Author red
as exactly 255,0,0. The paper-type choice is not in `dmMediaType`, which
stayed 0, so it lives in the 320 private bytes and is therefore carried by a
captured blob rather than by any portable field.

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
| `make-test-card.py` | generates a calibration card at any page size |
| `test-card-140x88.pdf` | calibration card for `HUB-CARD`, the ZC10L |
| `test-card-83.98x58.92.pdf` | calibration card for the Brother QL-800 |
| `spool\` | saved job PDFs. Safe to delete. Gitignored |
| `out.pdf` | output of the `HUB-PDF` queue. Overwritten each print. Gitignored |

`make-test-card.py` now takes optional arguments, and earlier notes saying
it takes none are out of date:

```
make-test-card.py                     -> 140.0 x 88.0, the ZC10L card
make-test-card.py 83.98 58.92 70 40   -> W H [h-target v-target]
```

The layout derives every position from `W` and `H`, and the caliper targets
shrink to fit, because a 100 mm target does not fit on a 84 mm label.

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

30. **The vendor-private region is universal, not a ZC10L quirk.** Every
    driver on this box reports a non-zero `dmDriverExtra`, spanning two
    orders of magnitude:

    | driver | public | private | total |
    |---|---|---|---|
    | Brother QL-800 | 220 | 320 | 540 |
    | Zebra ZC10L | 220 | 5836 | 6056 |
    | EPSON CW-C4000u | 220 | 30320 | 30540 |

    So capture and replay is product work rather than a tax this one
    uncertified driver imposes. Nothing can be configured portably on any of
    them. Note the Epson blob is 30 KB, which is large to carry per job but
    not a problem.
31. **The ten-second revert is ZC10L-specific.** Verified 19 found that a
    `SetPrinter` write to the queue default is re-asserted away by the ZC10L
    within about ten seconds. Brother and Epson both **held** the same write,
    a `dmCopies` flip, for 25 s with no drift.

    Read this carefully, because it narrows a claim rather than overturning
    a decision. Per-job DEVMODE stays the right design: it is the only one
    that works on all three drivers, and one code path beats two. But the
    reason is "the ZC10L defeats the queue default, and the agent must
    support the ZC10L", not "the queue default cannot be made to stick on
    Windows". The memo said the latter.
32. **Public `dmScale` is inert on every driver here.** Setting `dmScale` to
    105 or 50, with `DM_SCALE` set in `dmFields`, and handing the blob to
    `CreateDC` changed no reported geometry at all on Brother, Epson,
    ZC10L or the Microsoft PDF driver: same dpi, same pixel counts, same
    millimetres.

    A negative finding that matters twice. Product code that tries to scale
    through `dmScale` will silently do nothing. And the ZC10L's zoom, which
    provably does scale output (Verified 18), therefore lives entirely in
    the driver-private bytes. The scale hazard is reachable by no portable
    API, so pinning the private region is the only defence available on any
    driver.
33. **The Brother has unprintable margins. The other two do not.** Its
    physical page is 1061 x 342 px against an imageable 991 x 306, at a
    physical offset of 35, 18 px: about 2.96 mm at the left and 1.52 mm at
    the top, at 300 dpi. `HUB-CARD` and the Epson both report offset 0, 0
    with physical equal to imageable.

    So a full-bleed badge is impossible on the QL-800 and fine on the other
    two. `pdfium_print` centres within the imageable area, so it stays
    correct here, but any layout that assumes bleed does not travel.
34. Media models differ far more than the drivers do. Form counts are 1 for
    the ZC10L, 3 for the Epson and **58** for the Brother, which includes a
    literal `Visitor Name Badge Label` at 62 x 99.8 mm, paperkind 322. The
    Brother reports `colordevice 0`, so the QL-800's black-and-red DK media
    is not exposed as a colour device at all. The Epson reports
    `colordevice 1` at 600 dpi on a 108 mm roll, which makes it the only
    badge-capable colour device on the desk.

    Every driver's dpi and millimetre claims agree with each other at rest,
    within 0.4 mm. The disagreement in Verified 18 appears only when a
    vendor scale setting is engaged, so a consistency check is a valid
    detector but not a passive one.

35. **`GetPrinter` level 2 `pDevMode` carries stale geometry. Do not read
    it.** After the operator changed the Brother's form to `62mm` by hand,
    the stored default still reported `dmPaperWidth` 290, the 29 mm value
    from the form before it, while `dmPaperSize` had correctly moved to 259.
    `DocumentProperties` resolved the same queue to 620, and `CreateDC`
    agreed with `DocumentProperties`.

    So the driver updates the stored blob's paper *id* and fixes the
    dimensions up only at resolve time. `caps.py` had been reporting the
    stale source since it was written; it now delegates to `devmode.py`.
    `HUB-CARD` agrees across both sources, which is why this went unnoticed:
    its form has never been changed.
36. **The renderer works on a second driver, and the pin travels.**
    `pdfium_print` printed to the Brother QL-800 with a captured Brother
    blob pinned, reporting 300 dpi, 992 x 696 px, `clipped=False` and a
    scale error of 0.009 x 0.008 mm. So neither the PDFium path nor the
    per-job DEVMODE pin is specific to the ZC10L. Awaiting calipers.

37. **The Brother prints red while reporting that it cannot.** With
    black/red DK stock loaded and selected, a pure 255,0,0 bar and a line of
    pure red text both came out red on paper. The driver reports
    `DC_COLORDEVICE` 0 and `dmColor` 1, monochrome, throughout.

    So **never gate behaviour on a driver's colour claim.** Product code
    asking "is this a colour device?" would decide the QL-800 is monochrome,
    and any greyscale conversion done on the strength of that answer would
    silently destroy the second colour.

    Put this beside Verified 18 and read them together, because they are the
    same defect pointing opposite ways. The ZC10L **overstates** its
    resolution, reporting 315 dpi while printing at 300, and a card came out
    5% oversized. The Brother **understates** its colour, reporting a
    monochrome device while printing red. A driver's self-description is
    evidence, not truth. Only printed output settles anything, which is why
    every claim in this file that matters is backed by a physical card or
    label.

    Consequence for the still-open `monochrome` work from task 1: forcing
    `dmColor` is not obviously meaningful on a driver that ignores the field
    in one direction already. Test it on media before believing it.

    The separation rule is only half mapped. Confirmed on the label: `R`
    (255,0,0) prints red, `B` (0,0,255) prints black. So the printer sorts
    every pixel into red, black or white, and blue is not treated as
    near-red. Unknown: whether `M` (255,0,255) and `Y` (255,255,0) go red,
    which decides whether the rule is "exactly 255,0,0" or "red channel
    dominant". A badge author needs that answer, because under the second
    rule magenta silently becomes red.

38. **The Brother driver raises a modal dialog in the print path, and it is
    the only recovery route. This is a deployment blocker, and it is the
    driver's doing, not ours.** Sequence, measured:

    | t | event |
    |---|---|
    | idle, cover open | `Status 0x0`, WMI `Idle`, `Get-Printer` **Normal** |
    | POST + 2.1 s | job appears, `PRINTING\|RETAINED`, printer still `0x0` |
    | POST + 3.3 s | printer `0x00000002` **ERROR**, job `PAUSED\|ERROR\|PRINTING\|RETAINED` |
    | cover closed | **no state change at all for 45 s.** Job stays paused |
    | operator clicks Resume in the dialog | label prints immediately |

    Closing the cover does not recover the job. Only the dialog's Resume
    button did. So on a LocalSystem service in Session 0 there is no desktop
    to show that dialog and nobody to click it, and a cover-open leaves the
    job hung with no recovery path and no diagnosis. Design rule 5 says a
    dialog on a headless box is an outage; here the outage is imported with
    the driver and cannot be switched off from our side.

    Whether `SetJob` with `JOB_CONTROL_RESUME` substitutes for the click
    decides whether this is survivable. First attempt suggested it does not,
    but the trial was confounded. See Verified 41 and re-run it.

39. **The dialog names the fault in plain English while the API returns
    `Other`.** The popup read:

    ```
    61mm Continuous Length Tape - ql800-coveropen 62mm  Cover open.
    ```

    At that exact moment `DetectedErrorState` was `Other` (1),
    `ExtendedDetectedErrorState` was 1, and `ErrorDescription` was **empty**.

    So `Other` is not the driver failing to know. The driver knows, and
    routes the answer to a human on a screen instead of to the status API.
    On a headless box that information is destroyed rather than merely
    unavailable, which is worse than the ZC10L's silence: the ZC10L at least
    named `DOOR_OPEN` through the API.

40. **Fault attribution does not generalize, and the two drivers hide the
    truth in opposite places.**

    | | Zebra ZC10L | Brother QL-800 |
    |---|---|---|
    | cover open while **idle** | `DOOR_OPEN`, visible | nothing, reports `Normal` |
    | printer `Status` with a job | `DOOR_OPEN`, named | `ERROR`, generic |
    | job `Status` with a job | `PRINTING\|RETAINED`, lied | `PAUSED\|ERROR\|...`, flags it |
    | recovery | automatic, job reprints | needs a dialog click |
    | latency | ~1 s | ~3.3 s |

    Two memo claims fall as a result. The ZC10L's cover-open was the single
    fault visible while idle, so it was the only pre-flight signal that
    existed anywhere; it is Zebra-specific, and the Brother has none. And
    the promise that "the iPad can name the actual problem to a desk" is
    Zebra-specific too: on the Brother the agent can only say that it
    failed.

    Revise the implementation trap accordingly. CLAUDE.md said "job status
    lies, poll printer status". On the Brother it is the *job* status that
    carries the error bit the printer status will not name. **Read both,
    trust neither alone.**

41. **No programmatic recovery works on the QL-800. Only the dialog does.**
    Every job-control route was tried against a genuinely stuck job:

    | action | outcome |
    |---|---|
    | operator clicks Resume in the dialog | label prints. The only thing that works |
    | `JOB_CONTROL_RESUME` | job leaves the queue in 0.5 s, `Status` back to `0x0`, WMI `Idle`, no error raised, **no label**. Tried twice |
    | `JOB_CONTROL_RESTART` | job stays `PAUSED\|ERROR` for 20 s. The spooler sets the `RESTART` bit, the driver ignores it. Job survives |
    | fresh job while the stuck one is queued | **queues behind it and does not print.** Printer stays `ERROR` |
    | fresh job, no fault present | prints normally |

    `RESTART` fails better than `RESUME`: it leaves the badge in the queue
    instead of discarding it. Neither recovers.

    **A stuck job blocks everything behind it.** This is the operational
    fact that matters most. One unrecovered fault stops every subsequent
    badge, and the queue does not drain itself. So recovery by resubmission
    cannot work on its own; the blocker has to be cleared first.

    **The confound: the fault used was media-out, and the operator reports
    the roll may not have been properly seated when it went back in.** So
    the missing label has two candidate causes that this trial cannot
    separate, and the innocent one is at least as likely: a badly seated
    roll simply could not feed. That the next job printed does not settle it
    either, because a feed attempt can seat a roll.

    **The re-run with cover open gave the same result, and there is no
    clean fault available on this printer.** Opening the cover makes the
    QL-800 **retract the tape**, so the media has to be reloaded afterwards
    and is not under the head when a recovery is attempted. Cover-open,
    media-out and every other fault therefore share the same confound, and
    no induced fault leaves the media undisturbed. Only a USB disconnect
    would, and that may not pause the job at all.

    So stop trying to isolate the fault and explain the mechanism instead,
    because the data already contains the answer. A **fresh** job prints
    normally after a reload; a **resumed** job never does. A fresh job makes
    the driver re-feed and calibrate. `SetJob` `JOB_CONTROL_RESUME` releases
    the spooler's job without telling the driver to feed anything, so there
    is no media under the head and the page is discarded. The dialog's
    button and the API call act at different layers, which is why one works
    and the other does not.

    What rides on the answer, which is why it is worth another label. If
    resume recovers the job, the QL-800 is usable headless provided the
    agent detects `PAUSED|ERROR` and resumes, and that becomes a product
    requirement rather than an optimisation. If resume discards the job,
    the printer cannot run unattended at all **and** the first mitigation
    any engineer would reach for is a badge shredder that reports success.
    Those are opposite conclusions, so do not carry either into the memo
    until the clean run is done.

    Still genuinely open, and worth one clean test some other day:
    **delete the stuck job, then resubmit.** The attempt here was
    confounded, because the operator clicked Resume before the delete, so
    the queue was already healthy and the job that printed proves nothing
    about unblocking a stuck one. The agent holds the badge PDF, a fresh job
    demonstrably re-feeds, and resubmission uses no vendor job-control
    semantics, so it is the one candidate that could generalise. Do not
    assume it works.

    Note the framing this settles anyway. "Detect `PAUSED|ERROR` and
    resume" is a badge shredder that reports success, and it is the first
    thing any engineer would reach for. Write that down before somebody
    ships it as an obvious win.

    **The verdict does not depend on the open question.** Recovery needs a
    human at a desktop with a mouse, so the QL-800 cannot run unattended as
    it stands. Delete-and-resend would at worst make it recoverable, not
    self-explaining: the fault would still be unattributable and still
    invisible until a badge is sent.

42. **Third driver, and the pin travels again. The EPSON CW-C4000u prints
    correctly at 102 x 302 mm.** Pinned blob, 600 dpi, raster 2409 x 7134 px
    matching the printable area exactly on both axes, `clipped=False`, scale
    error 0.011 x 0.016 mm. The operator reports scale correct on both
    targets and colours good.

    Read the scale result as operator-confirmed rather than measured: no
    numeric caliper readings were given, so do not quote it as 0.00 mm the
    way the ZC10L cards can be. It is still the most sensitive scale check
    in this spike, because the vertical target is **250 mm** against the
    ZC10L's 100 mm, so a proportional error would show up two and a half
    times larger.

    Worth carrying separately:

    - **Offset 0, 0 and physical equal to imageable**, so full-bleed badges
      are possible here. The Brother cannot do that (Verified 33).
    - **First honest colour look in this project.** `colordevice 1`, a
      600 dpi CMYK inkjet, and unlike the Brother it is not lying about it.
      Every earlier colour observation came off either a JPEG-re-encoded PDF
      or a two-colour thermal printer.
    - **17.2 megapixels rendered and spooled in 1.35 s.** Useful for the
      child-process change on the later-tasks list: render cost is not what
      would make that change hurt.
    - The queue that works is `EPSON CW-C4000u (Copy 1)`. The bare
      `EPSON CW-C4000u` is an orphan: present to `EnumPrinters`, absent from
      the Windows printer list, and configured differently in the private
      region while identical in every public field. See the gotchas.

43. **Open: the badge did not auto-cut, and the cut setting is not a DEVMODE
    field.** There is no standard `DEVMODE` member for cutter behaviour, so
    on this driver it must live in the 30320 private bytes. That makes it
    the Epson's exact analogue of the ZC10L's `Zoom-in/out[Z]`, and a better
    one, because auto-cut is a production requirement rather than an
    artificial test setting: an uncut badge is not a usable badge.

    **The consequence is the important part. A hub deployed with a blob
    captured before auto-cut was enabled prints uncut badges forever, and
    nothing reports a problem.** Same silent-failure class as Verified 18's
    5% oversizing. This is why the rule is capture the blob *after*
    configuring the driver by hand, and it is now the second independent
    reason for that rule rather than a Zebra curiosity.

    Enabling auto-cut moved **19 private bytes and nothing public**, so the
    `dmDeviceName` residue trap from Verified 17 did not appear on this
    driver. Decoding them against known device numbers explains all but two:

    | private+ | a -> b | reading |
    |---|---|---|
    | 560, 564, 1980, 1996, 2036 | 2551 -> 2409 | page width px |
    | 568, 1984, 2000, 2040 | 4129 -> 7134 | page height px |
    | 592 | 4129 -> 7133 | page height - 1 |
    | **268** | 256 -> 65 | unexplained |
    | **600** | 1 -> 2 | unexplained. The cut-mode candidate |

    `+600` moving 1 to 2 is the plausible cut enum. The behavioural test
    below proves the cut setting is in one of those two offsets but cannot
    say which, and it does not need to.

    **Settled by a controlled pair, and it is the cleanest experiment in
    this spike.** Same PDF, same queue, same code path, with the queue
    default left at auto-cut ON throughout, so the only variable was the
    pinned blob:

    | pinned blob | badge |
    |---|---|
    | the pre-cut capture | **did not cut** |
    | the auto-cut capture | **cut** |

    The first row alone would have been ambiguous, since "pinning any blob
    suppresses cutting" explains it equally well. The second row excludes
    that, so the blob is carrying the setting rather than dropping it.

    Three things follow, and two of them generalise earlier single-driver
    claims:

    1. **Per-job DEVMODE beats the queue default on a second vendor.** The
       queue default said cut and the pinned blob said do not, and the blob
       won. Verified 20 was measured only on the ZC10L, and assuming Zebra
       behaviour generalises has been wrong twice today, so this is worth
       having.
    2. **Capture and replay carries a vendor-private setting that matters.**
       Spike 2's proof used `Zoom-in/out[Z]`, a setting invented for the
       test. Auto-cut is a production requirement.
    3. **The deployment hazard is now demonstrated rather than argued.** A
       hub pinned with a blob captured before auto-cut was configured prints
       uncut badges forever, while `/health` reports `scale_pinned: true`,
       the geometry reads correct to 0.016 mm, and nothing raises an error.

    **Prefer this pair over the zoom pair when showing the team.** Both
    demonstrate the same silent failure, but a 5% oversized card needs
    calipers to see, and an uncut badge is obviously wrong to anybody
    holding it. Keep the two Epson badges together.

44. **The private region carried stale geometry, and nothing visible said
    so.** The first Epson blob recorded page width 2551 px and height
    4129 px in its private bytes: the **old** 108 x 174.8 mm die-cut size.
    At the same moment the public section correctly said paperkind 256 at
    102 x 302 mm, and `CreateDC` plus `GetDeviceCaps` correctly reported
    2409 x 7134. The blob contradicted itself and no public field or live
    DC reading revealed it.

    Setting the media by hand did **not** refresh those private bytes. It
    took a second trip through the driver UI, for the cut setting, before
    the driver rewrote them. So "configure by hand, then capture" does not
    guarantee an internally consistent blob.

    **State the consequence carefully, because it is smaller than it
    looks.** The staleness had no observable effect. The DC built from that
    blob reported correct geometry and the badge printed at correct scale,
    so this driver resolves geometry from the public section and treats its
    private copy as derived. A driver that trusted its private geometry
    instead would misprint silently, but nothing here demonstrates that any
    driver does. Do not carry this to the memo as a live hazard.

    What it does establish is narrower and still useful: **the private
    region is not a reliable record of the queue's geometry, so never read
    geometry out of it.** Ask the driver. `pdfium_print --dry-run --devmode
    <blob>` already does exactly that, reporting printable px and mm from a
    DC built with the blob, which is why the stale blob was safe to pin: the
    check that matters was already in the path.

45. **Fourth printer prints, and the rig needed no change for any of them.**
    The ZD621 on the ZPL driver, 88 x 76 mm mark-sensed stock, pinned blob,
    203 dpi, raster 703 x 609 px matching the printable area exactly,
    `clipped=False`, scale error 0.002 x 0.010 mm, 0.79 s end to end. Full
    bleed, offset 0, 0.

    Four printers, four vendors' driver models, one code path, no
    conditionals. That is the strongest thing the spike can say about the
    Windows print path: **getting correct geometry onto media is solved and
    it generalises.**

    First sub-300 dpi device here, which makes the test card's ladders
    diagnostic rather than decorative for the first time. One dot is
    0.125 mm at 203 dpi, so the 0.1 pt hairline at 0.035 mm is under a third
    of a dot and 4 pt text has strokes thinner than one dot. Whatever
    happens to those is a resolution limit the agent cannot fix, and it
    bears on badge text directly.

46. **Two of two roll-fed printers defaulted to not cutting, and cut is
    never a DEVMODE field.** The Epson did not cut until the setting was
    enabled by hand (Verified 43), and the ZD621 did not either.

    Read that as the pattern it is. For roll-fed badge printers **the
    default failure mode is a badge still attached to the roll**, it is
    invisible to every portable API, and it is carried only by the captured
    blob. So the capture-after-configuring rule is not a Zebra curiosity or
    an Epson curiosity: it is the normal case for this class of hardware,
    and a hub commissioned with a blob captured too early produces uncut
    output on any of them while reporting success.

    Note the ZD621 caveat before treating it as identical: its cutter is an
    optional accessory rather than standard, so on this unit no driver
    setting will help unless the hardware is fitted. Check that before
    concluding the setting is missing.

47. **Cut replay proven on the ZD621 too, by a four-byte controlled pair.
    This is the cleanest settings result in the spike.** Queue default left
    at cut throughout, same PDF, same queue, same code path:

    | pinned blob | label |
    |---|---|
    | the cut capture | **cut** |
    | the tear-off capture | **did not cut** |

    The two blobs differ by **4 bytes out of 13702**, public section
    byte-identical: private+45 `0x00`->`0x01`, +803 `0x01`->`0x00`,
    +1612 `0x00`->`0x04`, +1696 `0x00`->`0x02`.

    **Why this beats the Epson's version of the same proof.** The Epson diff
    moved 19 bytes and 15 were page geometry its driver had not flushed yet
    (Verified 44), so someone could argue the geometry did the work. Here
    nothing but four flag bytes changed and the behaviour still flipped both
    ways. The vendor-private region is unambiguously what carries it.

    **Three vendors now, each with a production-relevant setting in bytes no
    portable API reaches, each carried by a captured blob, each overriding
    the queue default:** ZC10L zoom (4 bytes), Epson auto-cut, ZD621 cut
    mode (4 bytes). Spike 2's conclusion is no longer an extrapolation from
    one driver.

    **And it puts a number on the deployment risk.** Four bytes out of 13702
    separate a badge that cuts from one that does not. Both jobs reported
    `scale_pinned: true`, identical geometry to 0.002 mm, and byte-identical
    JSON. Nothing in `/health`, `/queue` or the print response can tell them
    apart. The only difference is in the operator's hand.

    Also carry this: private-region freshness is driver-dependent. Same
    capture sequence on both printers, and the ZD621 wrote its private
    geometry immediately on the media change while the Epson deferred it. So
    the "click through the dialog twice" precaution is Epson insurance, not
    a universal step. Harmless to keep, wrong to generalise.

48. **At 203 dpi a 0.1 pt hairline prints as scattered dots and 4 pt text
    is barely legible. This is a resolution limit, and no code can fix
    it.** Observed on the ZD621 label. Every other printer here is 300 or
    600 dpi, so this is the first time the rig's output was limited by the
    printer rather than by a driver or the renderer.

    The arithmetic, because it predicts the effect elsewhere. One dot at
    203 dpi is 0.125 mm, which is **0.355 pt**. So:

    | authored | in dots | observed |
    |---|---|---|
    | 0.1 pt = 0.035 mm | 0.28 dot | broken into dots |
    | 0.25 pt = 0.088 mm | 0.71 dot | not separately reported |
    | 0.5 pt = 0.176 mm | 1.41 dot | solid |

    PDFium rasterises antialiased, so a 0.28-dot line arrives as roughly 28%
    grey. A thermal head is **1-bit**: it either burns a dot or does not, so
    that grey is thresholded and what survives is a scatter of dots rather
    than a thin line.

    **Working floors for a 203 dpi device: lines no finer than 0.5 pt, text
    no smaller than 5 pt.** One dot, 0.355 pt, is the theoretical floor and
    it will look ragged.

    Likely mechanism for why this never appeared before, stated as a
    hypothesis rather than a finding: the ZC10L is a retransfer card printer
    and renders continuous tone, so a 28% grey line comes out as a thin grey
    line rather than breaking up. Thermal label printers cannot do that.
    **If that is right, the split is 1-bit devices against contone devices,
    not simply high dpi against low.** Untested; the ZC10L card's 0.1 pt rung
    was never examined closely.

    **The product consequence is a constraint on badge design, not on the
    agent.** Minimum legible type and line weight depend on the printer, and
    a template that looks right on the 600 dpi Epson degrades on a 203 dpi
    ZD621. So badge templates need either a declared minimum-resolution
    assumption or per-device variants. That belongs to whoever builds the
    badge designer, and it is worth telling them before they ship 4 pt
    disclaimer text.

49. **The DYMO 550 refuses non-genuine labels outright.** First print with
    third-party stock: printer `Status 0x00000002 ERROR`, job
    `ERROR|PRINTING|RETAINED`, and `pStatus` reading **`Unknown label
    detected`**. Job still stuck after 24 s, nothing printed.

    RFID media authentication is enforced, not advisory. This is a
    **consumables constraint, not a software one**: no driver setting, blob
    or code change reaches it, and the DYMO column of the benchmark cannot
    be completed without genuine DYMO stock. Worth knowing before anyone
    prices a DYMO into a venue kit, because the labels are the recurring
    cost and third-party is not an option.

50. **`pStatus` is not always empty, and on the DYMO it is the best fault
    report on the bench.** The spike 4 trap in Closed task 4 says
    "`pStatus` is always empty". That was true of the ZC10L and the Brother
    and it is **wrong in general**. The DYMO populates it with a
    human-readable sentence naming the actual fault.

    **All three printers put the truth in a different field.** This is the
    sharpest form of the rule and it should drive the implementation:

    | printer | printer `Status` | job `Status` | job `pStatus` |
    |---|---|---|---|
    | Zebra ZC10L | **named**, 4 codes | lies, reads `PRINTING` | empty |
    | Brother QL-800 | generic `ERROR` | **flags** `PAUSED\|ERROR` | empty |
    | DYMO 550 | generic `ERROR` | `ERROR`, not paused | **a sentence** |

    So the agent must read all three: the printer status bitfield, the job
    status bitfield, and the `pStatus` string. Any one of them alone is
    uninformative on at least one printer, and no two of them agree about
    where the information lives. Reading `pStatus` is nearly free and on the
    DYMO it is the difference between "it failed" and "wrong labels".

    Note the DYMO job is `ERROR` but **not** `PAUSED`, unlike the Brother's
    `PAUSED|ERROR`. So even the shape of a stuck job differs, and a
    detector keyed on `JOB_STATUS_PAUSED` would miss this one entirely.

    **The dialog channel inverts between the two vendors, and the DYMO
    picks the right one.** A dialog appeared on the DYMO too, briefly, and
    the operator reports it said only "error".

    | | dialog says | API says |
    |---|---|---|
    | Brother QL-800 | **"Cover open."**, specific | `Other (1)`, `pStatus` empty |
    | DYMO 550 | "error", generic | **"Unknown label detected"** |

    So neither vendor is better across the board; they choose different
    channels for the same information. But for a headless agent **the DYMO
    is the better citizen**, because the useful text is in the API where
    code can read it rather than on a screen in a session nobody is
    watching. Worth saying plainly, because the DYMO is also the printer
    that refused to print, and it would be easy to score it as the worst of
    the five on that basis alone.

    The DYMO dialog also dismissed itself rather than blocking, unlike the
    Brother's, which persisted and held the only working recovery. The job
    stayed stuck either way, so on the DYMO the dialog is not the recovery
    mechanism and is closer to a notification.

51. **The DYMO has the worst unprintable margins of the five.** Physical
    694 x 1200 px against an imageable 665 x 1112 at 300 dpi, at an
    asymmetric offset of 17, 70: **1.44 mm at the left and 5.93 mm at the
    top**, losing 2.46 mm of width and 7.45 mm of length overall. The
    Brother loses 2.96 / 1.52 mm; the other three lose nothing.

    It is also the loosest driver for geometry honesty here, claiming
    56 x 94 mm while its own pixel counts imply 56.30 x 94.15, deltas of
    0.30 and 0.15 mm. Inside the 1 mm consistency threshold, but several
    times the other printers' disagreement.

    One more stale-field case for the collection: after the media change
    `dmFormName` still read `30252 Address` while `dmPaperSize` had moved to
    paperkind 179. Same class as Verified 35 and 44. Do not trust a form
    name.

52. **All five printers on the desk print correct geometry through one
    unchanged code path.** The DYMO printed on genuine 30252 address labels:
    imageable 299 x 963 px at 300 dpi, raster matching exactly,
    `clipped=False`, scale error 0.005 x 0.004 mm, queue cleared to `0x0`
    with no error. Operator reports it looks good. Visual confirmation, not
    calipers, so do not quote a number for it.

    Clean contrast with the refused job: that one stuck at `ERROR` with
    `pStatus` set and never cleared. So the RFID rejection was specifically
    the third-party labels, not the queue, the driver or the rig.

    | printer | dpi | media | result |
    |---|---|---|---|
    | Zebra ZC10L | 300 | 140 x 88 mm PVC card | calipers 100.00 / 50.00 |
    | Brother QL-800 | 300 | 62 mm continuous DK | operator confirmed |
    | EPSON CW-C4000u | 600 | 102 x 302 mm badge stock | confirmed, 250 mm target |
    | Zebra ZD621 | 203 | 88 x 76 mm mark-sensed | printed, calipers pending |
    | DYMO 550 Turbo | 300 | 28.6 x 88.9 mm address label | operator confirmed |

    **Five printers, four vendors' driver models, 203 to 600 dpi, PVC card
    through continuous tape through die-cut label through folded badge
    stock. No conditionals anywhere in the renderer.** That is the strongest
    statement the spike can make, and it is now measured rather than argued:
    *getting correct geometry onto media is solved, and it generalises.*

    Set against it, the fault side generalised to nothing. Three printers
    were broken deliberately and each put the truth in a different API
    field. Whatever the memo says about the print path, it must not extend
    that confidence to reporting.

53. The test card generator gained a **narrow-media layout**, because the
    standard one needs roughly 60 mm of width and a DYMO address label is
    28.6 mm. On narrow pages the long axis does the measuring: one long
    vertical caliper target, and the **corner crosses as the horizontal
    target**, since their spacing is an exact known distance. No ruler,
    because on a page that narrow it would have to cross the vertical
    target. It reports which layout it used.

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
| `QL800.62mm-blackred.devmode` | Brother, 62 mm tape, black/red stock |
| `C4000u.102x302-blackmark.devmode` | Epson, 102 x 302 mm, **cut OFF.** The teaching artefact, not for use |
| `C4000u.102x302-autocut.devmode` | Epson, 102 x 302 mm, **cut ON.** Pin this one |
| `ZD621.factory.devmode` | ZD621 as installed, 104 x 76.2 mm. Untouched factory state |
| `ZD621.88x76-mark.devmode` | ZD621, 88 x 76 mm mark-sensed, **tear-off.** Teaching artefact |
| `ZD621.88x76-mark-cut.devmode` | ZD621, 88 x 76 mm mark-sensed, **cut ON.** Pin this one |

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
- **`pStatus` is empty on the ZC10L and the Brother, and carries a
  human-readable sentence on the DYMO 550.** The claim below that it is
  "always empty" was measured on two printers and is wrong in general. See
  Verified 50: read the printer status bitfield, the job status bitfield and
  the `pStatus` string, because the three printers tested put the truth in
  three different places.
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

## Architecture direction: the hub is the fallback, not the universal path

Set by the operator after the QL-800 fault work. Recorded here because it
changes what this rig is for, and therefore which findings matter.

**Direct vendor SDK where one exists. The Windows hub only where none
does.** PheedLoop already connects the OnSite app straight to the EPSON
ColorWorks, so the pattern is proven in the product rather than
hypothetical. Brother publishes an SDK too, so the QL-800 is a candidate for
the same treatment.

What that does to this spike's conclusions:

- **The hub's target set narrows to printers with no usable SDK**, which
  today means the ZC10L card printer. That is the best-behaved driver
  tested: it names four faults through the API and recovers automatically.
  Verified 38 to 41, the whole QL-800 catalogue of dialogs and silent
  discards, stops being the hub's problem if the Brother goes direct.
- The narrowing is good news. The hub does not have to be a universal
  Windows print layer, which is the version of it that the driver diversity
  work was making look expensive.
- It also redirects the remaining printer testing. A ZD621 or DYMO 550 is
  only worth putting through the hub if it would actually ship that way.
  Both have their own direct paths, and Zebra label printers speak ZPL, so
  the honest question for each is "SDK or hub", asked before any driver work.

**Verify first, because it gates the whole idea: can an iPad reach a QL-800
at all?** This unit is on USB003 and Brother's networked models are
different part numbers. If the QL-800 is USB-only then no direct app
connection is possible without changing the hardware, and the SDK path
applies to a QL-820NWB or similar instead. Check that before any SDK work.
Also confirm the SDK reports faults *with attribution*, since the Windows
driver's generic `ERROR` is the thing being escaped.

### The display, and what it can honestly say

A display on the hub is the right surface for errors, and it works
**because** the ZC10L names its faults. `/queue` already returns the status
integer, so no rig change is owed.

Two limits it must respect, both measured:

1. **It can never show "ready".** No fault is visible while the queue is
   idle, so a green light would be a lie. It shows the last job's outcome.
2. **It only speaks for printers the hub is in the path of.** A badge sent
   direct from the app to an Epson never touches the hub, so the hub's
   display cannot report its errors. Error surfacing has to follow the print
   path, which means the direct-SDK printers need the app to surface their
   own faults.

### "We've sent your badge to the printer" is the right wording

The app staying naive is correct, and design rule 2 is now evidence rather
than caution: `sent` is the only word the API can support. The rig returned
`state: sent` with correct geometry for a printer that was physically
unplugged.

One gap worth closing cheaply. The error appears on the hub's display, and
the person who sent the badge is at an iPad, possibly not looking at it. So
**have the app poll the hub a few seconds after sending.** The ZC10L reports
a fault about a second after the job arrives, so a poll at three to five
seconds catches it, and the app can follow "sent" with "the printer reported
no cards" without ever claiming a badge exists. That keeps the honest
wording and still tells the person the thing they need to know.

## Later tasks, in order

Numbering here used to skip 2. It was a typo, not a deleted task.

1. Move rendering into a child process. PDFium runs in-process today, so a
   malformed PDF that crashes it takes the whole agent down. The renderer
   choice itself is settled, so this is the last piece of it outstanding.
   The bake-off is closed: the alternative could not print a card at all,
   and the GPLv3 dependency is retired.
2. Make the dedupe log durable on disk with a 24 hour window. It is in memory
   today.
3. **Done.** The Brother QL-800 and EPSON CW-C4000u are both installed, so
   text and colour checks no longer cost PVC. A Zebra ZD621 and a DYMO 550
   Turbo are also on the desk, not yet installed.

### Blocked on hardware we do not have on the desk yet

Logged rather than done. Do not start these without the device.

4. **Poll the hub from the app a few seconds after sending, and surface the
   fault.** Needs an iPad, and there is no iPad in this testing yet. The app
   keeps saying "we've sent your badge to the printer", then follows with
   whatever the printer reported. The ZC10L reports a fault about one second
   after the job arrives, so a poll at three to five seconds catches it.
   `/queue` already returns the printer `Status` integer, so the rig owes
   nothing to this: `16` is out of cards, `8` jammed, `262144` no ribbon,
   `4194304` cover open.

   The gap it closes: the fault lands on the hub's display and the person
   who sent the badge is at an iPad, possibly across the room from it.
5. **Check whether an iPad can reach a QL-800 at all.** This gates the whole
   Brother SDK idea and costs nothing but a spec sheet. The unit here is on
   USB003, and Brother's networked models carry different part numbers. If
   it is USB-only there is no direct app connection without changing
   hardware, and the SDK path belongs to a QL-820NWB or similar instead.
6. **Confirm the Brother SDK reports faults with attribution.** The thing
   being escaped is the Windows driver's generic `ERROR`, which cannot tell
   out-of-labels from cover-open. An SDK that reports its own generic error
   buys nothing. Check before committing to the direct path.

### Open experiments that need no new hardware

7. **Delete the stuck job, then resubmit, on a genuinely stuck queue.** The
   one recovery route not yet ruled out on the QL-800, per Verified 41. The
   previous attempt was confounded. Costs one label.
8. Test whether SumatraPDF can open the Brother and Epson queues. Free
   against paused queues, and it settles how much of Closed task 1 is the
   ZC10L driver being an outlier rather than the renderer being weak.
9. Establish the Brother's two-colour separation rule: do `M` and `Y` print
   red, or only exact 255,0,0? Verified 37 has `R` red and `B` black. One
   label, and it decides how a badge may be authored.

## Explicitly out of scope this week

- The cloud transport and the WebSocket. All the risk sits in the Windows
  print path. Add the transport in week two when it is the only thing left.
- Reverse-engineering the Canon CX-G6400 wire format. A firmware update would
  own us. That printer is not on the desk yet anyway.
- The headless bootstrap ladder and the Wi-Fi hotspot rung. Earlier notes
  deferred these to "the mini PC", which is this box, so the hardware
  blocker is gone and only the week's sequencing defers them now.
- **The web interface. Deferred, not rejected.** It is expected in the
  finished product, and spike 4 gave it a concrete job: the agent can never
  pre-flight the printer, so staff need a surface that shows the last job's
  fault rather than a green light that cannot exist. `/queue` already
  returns the printer `Status` integer, so the data is in hand whenever
  product work picks this up. Nothing about it answers a memo question, so
  it waits.
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
- **A queue can exist for the print API and not for the Windows UI.**
  `EPSON CW-C4000u` is enumerated by `EnumPrinters` and absent from the
  Windows printer list, while `EPSON CW-C4000u (Copy 1)` is the real one.
  Their public `DEVMODE` fields are identical and their private regions
  differ, so nothing visible tells them apart. `/printers` would happily
  offer the agent a queue nobody can see or fix. Never assume an enumerated
  queue is a usable one.
- **A driver's own capability reports can be wrong in either direction.**
  `LOGPIXELSX` overstated resolution on the ZC10L (Verified 18) and
  `DC_COLORDEVICE` understated colour on the Brother (Verified 37). Treat
  every driver claim as a hypothesis to be checked against media.
- **Two ways to read a queue's default DEVMODE disagree.** `GetPrinter`
  level 2 `pDevMode` is the *stored* default and can hold geometry the
  driver no longer uses; `DocumentProperties` with `DM_OUT_BUFFER` is the
  *resolved* default and matches what `CreateDC` actually builds. Always
  read the resolved one. See Verified 35 for the case that caught this.
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