# Print Hub API for the OnSite app

**API v1.** Base path `/api/v1`. No authentication yet — pairing is
ENG-3781 and will add a token to the QR below. Do not ship against this on a
network you do not control.

## What the hub does and does not do

The hub **routes a job to a printer**. It does not publish page sizes, media
types or driver settings, and it will not tell you which badge belongs on
which printer. That is the app's decision. A hub that published its media
assumptions would invite you to trust them, and they are not reliable enough
to trust: drivers on this bench have reported the wrong resolution and denied
having colour they demonstrably print.

The hub applies its own per-printer driver configuration when it has one. You
do not need to know about it and cannot set it.

## 1. Find the hub

```
GET /api/v1/hub
```

```json
{
  "hub_id": "hub_52e94859b1ad",
  "name": "PheedLoop-Labs",
  "api_version": "1",
  "address": "192.168.1.30",
  "addresses": ["192.168.1.30"],
  "port": 8080,
  "base_url": "http://192.168.1.30:8080",
  "endpoints": {
    "hub": "/api/v1/hub",
    "printers": "/api/v1/printers",
    "print": "/api/v1/print",
    "job": "/api/v1/jobs/{job_id}"
  }
}
```

**Read `endpoints` rather than hardcoding paths.** A hub on an older build
can then advertise fewer of them without the app guessing.

`address` is the one to use. A hub may have several interfaces, and the hub
already excludes addresses that look real and cannot be reached.

`GET /api/v1/qr.png` is the same base URL as a QR, so nobody types an address
on an iPad. Do not cache it: once pairing lands it carries a credential.

## 2. List printers

```
GET /api/v1/printers
```

```json
{
  "hub_id": "hub_52e94859b1ad",
  "printers": [
    {"printer_id": "prn_47a5af920db2", "name": "zd621",
     "queue": "ZDesigner ZD621-203dpi ZPL", "accepting": true, "reason": null},
    {"printer_id": "prn_67f46fa27e75", "name": "zc10l",
     "queue": "HUB-CARD", "accepting": false, "reason": "offline"}
  ]
}
```

**Address printers by `printer_id`, never by name.** Ids are stable across
hub restarts and across a printer being removed and re-added. Names are for
showing to people and can change. `queue` is the underlying Windows name,
included for support conversations only.

### `accepting` is not "ready"

It means the hub would take a job for that printer right now. It is **not** a
health claim. No printer on this bench reports a fault until a job is
actually sent, so a printer that is accepting may still be out of ribbon,
jammed, or have its lid open.

Render it as *can be sent to*. **Do not render it as a green light.** The
only honest way to learn a printer's state is to send something and look at
what came back.

Current `reason` values when `accepting` is false: `offline`,
`opens_dialog`.

## 3. Send a job

```
POST /api/v1/print
Content-Type: multipart/form-data

pdf=<file>  printer_id=prn_...  job_id=<your id>
```

**The app generates `job_id`.** Redelivery is normal, not exceptional: resend
the same `job_id` freely after a timeout or a dropped connection and the hub
will not print a second badge. It answers `"deduped": true` instead.

```json
{"job_id": "onsite-e2b79c9b", "state": "sent",
 "printer_id": "prn_47a5af920db2", "clipped": false,
 "note": "sent to the spooler, which is not a promise that a badge exists"}
```

`clipped` is true when the PDF did not fit the printable area. The hub prints
it anyway, because you are better placed to decide whether that matters.

### Refusals

The hub refuses rather than accepting a job it knows will not produce a
badge. All refusals carry `state: "refused"` and a machine-readable `reason`:

| reason | HTTP | meaning |
|---|---|---|
| `unknown_printer` | 404 | no printer with that id; re-fetch the list |
| `offline` | 409 | the printer is reported offline |
| `opens_dialog` | 409 | that queue prompts for a filename and would hang |
| `no_pdf` | 400 | no `pdf` form field |

A refusal is **not** counted for deduplication. Once the cause is fixed,
resend the same `job_id` and it will print.

## 4. Find out what happened

```
GET /api/v1/jobs/{job_id}
```

```json
{"job_id": "onsite-e2b79c9b", "state": "cleared", "printer": "zd621",
 "detail": "Left the spooler. This does not mean a badge exists.",
 "fault": null, "events": ["accepted", "sent", "spooled", "cleared"]}
```

**Poll this three to five seconds after sending.** A printer reports a fault
about a second after the job reaches it, so that window catches the cause.
Below one second you may see nothing yet; much beyond five and the job has
usually left the queue.

| state | meaning |
|---|---|
| `accepted` | the hub took the job |
| `sent` | rendered and handed to the spooler |
| `spooled` | seen in the print queue |
| `cleared` | left the print queue |
| `fault` | a fault was reported while it was in flight; see `fault` |
| `failed` | the hub could not render or send it |
| `refused` | the hub declined it; see the refusal table |

### There is no `printed`, and there will not be one

Nothing in the Windows print path can confirm a badge physically reached a
tray. `cleared` means the spooler released the job, which happens whether or
not anything came out — during testing this software reported a completely
successful job, with correct geometry, for a printer that was unplugged.

**Tell the operator "we've sent your badge to the printer", never "printed".**
Then follow it with whatever the poll reports. If a fault comes back you can
name the cause — out of cards, ribbon out, jammed, cover open — which is
genuinely useful. If nothing comes back, say nothing more; silence is not
confirmation.
