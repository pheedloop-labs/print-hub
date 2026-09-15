# Hub console

The hub has no monitor. This is the only UI it has, and it is read from a
phone or a laptop on the same network.

    npm install
    npm run dev      # :5173, /api proxied to the hub on :8080. No rebuilds.
    npm run build    # -> ../printhub/static/, which Flask serves at /

From the repo root, `hub.ps1 console` and `hub.ps1 build` do the same two
things, and `hub.ps1 status` flags the build having gone stale against
`src/`.

**Node is a dev-machine dependency only.** A hub serves the built output in
`printhub/static/`, which is committed, so standing one up on a plain
machine needs Python and nothing else.

## Two rules the UI is not allowed to break

**No printer is ever shown as ready.** Every fault these printers can have —
empty hopper, ribbon out, jam, cover open — reads as a perfectly healthy
queue until a job is actually sent. A green light would be a claim the hub
cannot support. `StatusPill.svelte` renders a quiet queue as grey
"No fault reported", and that wording is load-bearing.

**A job is sent, never printed.** Nothing in the print path can confirm a
badge reached a tray. The spike returned success, with geometry correct to
0.01 mm, for a printer that was physically unplugged.

Both are findings from the spike, not preferences. See `CLAUDE.MD`,
Verified 29 and 55, and the design rules.

## Design system

`src/app.css` carries PheedLoop's ditto tokens in ditto's own shape — raw
ramps as space-separated RGB triplets, consumed as `rgb(var(--token))`, with
semantic aliases on top. A value changed in ditto pastes straight in.
Theming is on a `.dark` class, as ditto does it; `main.js` sets that class
from the device preference, so an in-app toggle later is a one-line change.

Poppins is **self-hosted** via `@fontsource`, latin subset only. The hub runs
on a network PheedLoop supplies, which may have no route to the internet, and
a Google Fonts link would silently fall back to a system font and stop
looking like PheedLoop. The bare `@fontsource/poppins/400.css` imports also
drag in the Devanagari subset and legacy `.woff`, about 280 kB this console
never renders, so the imports are `latin-` prefixed.

Not lifted from ditto: the purple and pink ramps, and the greeting and login
illustration sizes. Nothing here uses them.

One deliberate divergence. ditto has a success green, and this console does
not use it for printer state. See the rules above.

## Layout

    src/
      main.js                 mount, and the .dark class from the device
      App.svelte              shell: header, nav, connection state
      app.css                 design tokens. `idle` is grey on purpose
      lib/
        api.js                fetch wrappers
        hub.svelte.js         polling, keeps the last good reading
        router.svelte.js      hash router, ~30 lines
      components/
        StatusPill.svelte     the component that must not lie
        PrinterCard.svelte    one printer, and which source reported what
        QueueTable.svelte     what is in a spooler right now
        TestPageButton.svelte confirms first, warns harder when offline
      routes/
        Printers.svelte       the grid                        ENG-3782
        Printer.svelte        one printer: spooler, driver, config, history
        Queue.svelte          every spooler, globally
        Jobs.svelte           the job record                  ENG-3783

Routes are hashes (`#/printers/<queue>`), because Flask serves this from a
static folder and a real path would 404 on refresh.

**Two different things get called "queue".** Spooler is what is in the
spooler *right now* and is normally empty, since a job passes through in
about 1.4 seconds. Jobs is the record of what the hub was asked to print,
written by a watcher polling at 0.5 s. An empty Spooler view proves nothing
either way.

Still to build: per-printer configuration (ENG-3784) and pairing (ENG-3781).
