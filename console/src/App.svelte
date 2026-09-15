<script>
  import { onMount } from 'svelte'
  import { HubState } from './lib/hub.svelte.js'
  import { Router, go } from './lib/router.svelte.js'
  import Connect from './routes/Connect.svelte'
  import Jobs from './routes/Jobs.svelte'
  import Printer from './routes/Printer.svelte'
  import Printers from './routes/Printers.svelte'
  import Queue from './routes/Queue.svelte'

  const hub = new HubState(2000)
  const router = new Router()

  onMount(() => hub.start())

  // Anything held in a spooler right now, across every queue. This is the
  // number worth carrying in the nav: it is normally zero, so a non-zero one
  // means something is waiting.
  let inFlight = $derived(
    hub.printers.reduce((n, p) => n + (p.jobs?.length ?? 0), 0)
  )

  // The hub answering at all is separate from a printer being well. Both are
  // shown, and neither is allowed to imply the other.
  let connected = $derived(!hub.error && hub.data !== null)
</script>

<header class="bar">
  <div class="bar-inner">
    <div class="brand">
      <!-- Single-colour wordmark on transparent, so it needs no dark-mode
           variant: PheedLoop blue reads on both surfaces. -->
      <img class="logo" src="/pheedloop-logo.png" alt="PheedLoop" />
      <span class="divider" aria-hidden="true"></span>
      <div class="titles">
        <h1>Print Hub</h1>
        <p class="sub mono">{hub.hub?.queue ?? 'no queue set'}</p>
      </div>
    </div>

    <div class="meta">
      {#if hub.hub && !hub.hub.scale_pinned}
        <span
          class="chip warn"
          title="Jobs inherit the queue default, which a driver UI change moves under you"
        >
          scale not pinned
        </span>
      {/if}
      <span class="chip link" class:down={!connected}>
        {#if connected}
          hub reachable
        {:else if hub.loading}
          connecting…
        {:else}
          no answer
        {/if}
      </span>
    </div>
  </div>
</header>

<div class="shell">
  {#if hub.error && hub.data}
    <p class="stale">
      Showing the last reading from {hub.staleSeconds}s ago — the hub is not
      answering right now ({hub.error}).
    </p>
  {:else if hub.error}
    <p class="stale">Cannot reach the hub: {hub.error}</p>
  {/if}

  <nav>
    <button class:on={router.view === 'printers'} onclick={() => go('printers')}>
      Printers
      <span class="n">{hub.printers.length}</span>
    </button>
    <button class:on={router.view === 'queue'} onclick={() => go('queue')}>
      Spooler
      <span class="n">{inFlight}</span>
    </button>
    <button class:on={router.view === 'jobs'} onclick={() => go('jobs')}>
      Jobs
      <span class="n">{hub.jobs.length}</span>
    </button>
    <button class:on={router.view === 'connect'} onclick={() => go('connect')}>
      Connect
    </button>
  </nav>

  <main>
    {#if router.view === 'printers' && router.queue}
      <Printer {hub} queue={router.queue} />
    {:else if router.view === 'queue'}
      <Queue {hub} />
    {:else if router.view === 'jobs'}
      <Jobs {hub} queue={router.queue} />
    {:else if router.view === 'connect'}
      <Connect />
    {:else}
      <Printers {hub} />
    {/if}
  </main>
</div>

<style>
  .bar {
    background: rgb(var(--surface-contrast));
    border-bottom: 1px solid rgb(var(--border-neutral-light));
    position: sticky;
    top: 0;
    z-index: 10;
  }

  .bar-inner {
    max-width: 1100px;
    margin: 0 auto;
    padding: var(--sp-xs) var(--sp-s);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--sp-xs);
    flex-wrap: wrap;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: var(--sp-xs);
    min-width: 0;
  }

  .logo {
    height: 22px;
    width: auto;
    display: block;
    flex: none;
  }

  .divider {
    width: 1px;
    height: 24px;
    background: rgb(var(--border-neutral));
    flex: none;
  }

  .titles {
    min-width: 0;
  }

  h1 {
    font-size: var(--font-size-lg);
    line-height: var(--line-height-lg);
    font-weight: var(--font-semibold);
  }

  .sub {
    margin: 0;
    color: rgb(var(--text-caption));
    overflow-wrap: anywhere;
  }

  .meta {
    display: flex;
    align-items: center;
    gap: var(--sp-xxs);
    flex-wrap: wrap;
  }

  .chip {
    border-radius: 999px;
    padding: 3px var(--sp-xs);
    font-size: var(--font-size-sm);
    line-height: var(--line-height-sm);
    font-weight: var(--font-medium);
    border: 1px solid transparent;
  }

  .link {
    color: rgb(var(--text-caption));
    background: rgb(var(--surface-muted));
  }

  .link.down {
    color: rgb(var(--state-fault-fg));
    background: rgb(var(--state-fault-bg));
    border-color: rgb(var(--state-fault-fg) / 0.3);
  }

  .warn {
    color: rgb(var(--state-warn-fg));
    background: rgb(var(--state-warn-bg));
    border-color: rgb(var(--state-warn-fg) / 0.3);
  }

  .shell {
    max-width: 1100px;
    margin: 0 auto;
    padding: var(--sp-m) var(--sp-s) var(--sp-xl);
  }

  nav {
    display: flex;
    gap: var(--sp-xxs);
    margin-bottom: var(--sp-m);
  }

  nav button {
    font: inherit;
    font-size: var(--font-size-base);
    font-weight: var(--font-medium);
    display: inline-flex;
    align-items: center;
    gap: var(--sp-xxs);
    padding: 6px var(--sp-s);
    border-radius: 999px;
    border: 1px solid rgb(var(--border-neutral-light));
    background: rgb(var(--surface-contrast));
    color: rgb(var(--text-caption));
    cursor: pointer;
  }

  nav button:hover:not(.on) {
    color: rgb(var(--text-body));
    border-color: rgb(var(--border-neutral));
  }

  nav button.on {
    background: rgb(var(--surface-primary));
    border-color: rgb(var(--surface-primary));
    color: rgb(var(--text-invert));
  }

  nav .n {
    font-size: var(--font-size-xs);
    padding: 0 6px;
    border-radius: 999px;
    background: rgb(var(--surface-muted));
    color: rgb(var(--text-caption));
  }

  nav button.on .n {
    background: rgb(var(--white) / 0.25);
    color: rgb(var(--text-invert));
  }

  .stale {
    margin: 0 0 var(--sp-s);
    padding: var(--sp-xs) var(--sp-s);
    border-radius: var(--rounded-m);
    background: rgb(var(--state-warn-bg));
    color: rgb(var(--state-warn-fg));
    border: 1px solid rgb(var(--state-warn-fg) / 0.3);
    font-size: var(--font-size-sm);
    line-height: var(--line-height-sm);
  }
</style>
