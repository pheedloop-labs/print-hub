<script>
  import { onMount } from 'svelte'
  import { getHub, getAppPrinters } from '../lib/api.js'

  let hub = $state(null)
  let printers = $state([])
  let error = $state(null)
  let copied = $state(null)

  onMount(async () => {
    try {
      const [h, p] = await Promise.all([getHub(), getAppPrinters()])
      hub = h
      printers = p.printers
    } catch (err) {
      error = err.message
    }
  })

  async function copy(text, what) {
    try {
      await navigator.clipboard.writeText(text)
      copied = what
      setTimeout(() => (copied = null), 1500)
    } catch {
      copied = null
    }
  }
</script>

<section>
  <div class="head">
    <h2>Connect the OnSite app</h2>
    <p class="count">Everything the app needs to reach this hub</p>
  </div>

  {#if error}
    <p class="bad">Could not read the hub's identity: {error}</p>
  {:else if !hub}
    <p class="muted">Reading…</p>
  {:else}
    <div class="top">
      <div class="ident">
        <dl>
          <dt>Hub address</dt>
          <dd>
            <button class="copy" onclick={() => copy(hub.base_url, 'url')}>
              <span class="mono big">{hub.base_url ?? 'no routable address'}</span>
              <span class="hint">{copied === 'url' ? 'copied' : 'copy'}</span>
            </button>
          </dd>

          <dt>Hub id</dt>
          <dd>
            <button class="copy" onclick={() => copy(hub.hub_id, 'id')}>
              <span class="mono">{hub.hub_id}</span>
              <span class="hint">{copied === 'id' ? 'copied' : 'copy'}</span>
            </button>
          </dd>

          <dt>Machine</dt>
          <dd class="mono">{hub.name}</dd>

          <dt>API version</dt>
          <dd class="mono">v{hub.api_version}</dd>
        </dl>

        {#if hub.addresses?.length > 1}
          <p class="muted small">
            This machine has more than one address. The app should use
            <span class="mono">{hub.address}</span>; the others are listed only
            for diagnosis.
          </p>
        {/if}
      </div>

      {#if hub.base_url}
        <figure class="qr">
          <img src="/api/v1/qr.png" alt="QR code for {hub.base_url}" />
          <figcaption>Scan rather than typing an address</figcaption>
        </figure>
      {/if}
    </div>

    <h3>Endpoints</h3>
    <ul class="endpoints">
      {#each Object.entries(hub.endpoints ?? {}) as [name, path]}
        <li>
          <span class="verb">{name === 'print' ? 'POST' : 'GET'}</span>
          <span class="mono">{path}</span>
        </li>
      {/each}
    </ul>
    <p class="muted small">
      Fetch <span class="mono">/api/v1/hub</span> to discover these rather than
      hardcoding them, so an older hub can advertise fewer without the app
      guessing.
    </p>

    <h3>Printer ids</h3>
    <p class="muted small">
      The app addresses a printer by id. Names change; ids do not.
    </p>
    <ul class="printers">
      {#each printers as p (p.printer_id)}
        <li class:off={!p.accepting}>
          <button class="copy" onclick={() => copy(p.printer_id, p.printer_id)}>
            <span class="mono id">{p.printer_id}</span>
            <span class="hint">{copied === p.printer_id ? 'copied' : 'copy'}</span>
          </button>
          <span class="pname">{p.name}</span>
          {#if !p.accepting}
            <span class="why">not accepting — {p.reason}</span>
          {/if}
        </li>
      {/each}
    </ul>

    <p class="caveat">
      <strong>The hub routes, it does not choose.</strong> It publishes no page
      sizes, media or driver settings: sending the right badge to the right
      printer is the app's decision. <strong>"Accepting" is not "ready"</strong>
      — no printer here reports a fault until a job is actually sent, so a
      printer that accepts a job may still be out of ribbon, jammed or open.
      Poll the job three to five seconds after sending to find out.
    </p>
  {/if}
</section>

<style>
  .head {
    margin-bottom: var(--sp-s);
  }

  h2 {
    font-size: var(--font-size-xl);
    line-height: var(--line-height-xl);
  }

  h3 {
    font-size: var(--font-size-base);
    margin: var(--sp-m) 0 var(--sp-xxs);
  }

  .count,
  .muted {
    margin: 0;
    color: rgb(var(--text-caption));
    font-size: var(--font-size-sm);
  }

  .small {
    font-size: var(--font-size-xs);
    line-height: var(--line-height-sm);
    margin-top: var(--sp-xxs);
  }

  .bad {
    color: rgb(var(--state-fault-fg));
  }

  .top {
    display: flex;
    gap: var(--sp-m);
    flex-wrap: wrap;
    align-items: flex-start;
    background: rgb(var(--surface-contrast));
    border: 1px solid rgb(var(--border-neutral-light));
    border-radius: var(--rounded-l);
    padding: var(--sp-s);
  }

  .ident {
    flex: 1 1 280px;
    min-width: 0;
  }

  dl {
    margin: 0;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: var(--sp-xxs) var(--sp-s);
    align-items: baseline;
  }

  dt {
    color: rgb(var(--text-subtle));
    font-size: var(--font-size-xs);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  dd {
    margin: 0;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .big {
    font-size: var(--font-size-lg);
    font-weight: var(--font-medium);
  }

  .copy {
    font: inherit;
    display: inline-flex;
    align-items: baseline;
    gap: var(--sp-xxs);
    background: none;
    border: none;
    padding: 0;
    color: inherit;
    cursor: pointer;
    text-align: left;
    min-width: 0;
  }

  .copy:hover .hint {
    opacity: 1;
  }

  .hint {
    font-size: var(--font-size-xs);
    color: rgb(var(--text-link));
    opacity: 0.45;
    flex: none;
  }

  .qr {
    margin: 0;
    flex: none;
    text-align: center;
  }

  .qr img {
    width: 148px;
    height: 148px;
    display: block;
    background: rgb(var(--white));
    border-radius: var(--rounded-m);
    padding: var(--sp-xxs);
  }

  .qr figcaption {
    margin-top: var(--sp-xxs);
    color: rgb(var(--text-subtle));
    font-size: var(--font-size-xs);
  }

  .endpoints,
  .printers {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .endpoints li,
  .printers li {
    display: flex;
    align-items: baseline;
    gap: var(--sp-xs);
    flex-wrap: wrap;
    padding: 5px var(--sp-xs);
    background: rgb(var(--surface-contrast));
    border: 1px solid rgb(var(--border-neutral-light));
    border-radius: var(--rounded-s);
    font-size: var(--font-size-sm);
  }

  .printers li.off {
    background: transparent;
    border-style: dashed;
  }

  .verb {
    font-size: var(--font-size-xs);
    font-weight: var(--font-semibold);
    color: rgb(var(--text-primary));
    min-width: 4ch;
  }

  .id {
    color: rgb(var(--text-heading));
  }

  .pname {
    color: rgb(var(--text-caption));
  }

  .why {
    margin-left: auto;
    color: rgb(var(--state-warn-fg));
    font-size: var(--font-size-xs);
  }

  .caveat {
    margin: var(--sp-m) 0 0;
    color: rgb(var(--text-subtle));
    font-size: var(--font-size-sm);
    line-height: var(--line-height-lg);
    border-top: 1px solid rgb(var(--border-neutral-light));
    padding-top: var(--sp-s);
    max-width: 68ch;
  }
</style>
