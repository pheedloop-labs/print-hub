<script>
  import { onMount } from 'svelte'
  import { HubState } from './lib/hub.svelte.js'
  import Printers from './routes/Printers.svelte'

  const hub = new HubState(2000)

  onMount(() => hub.start())

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

  <main>
    <Printers {hub} />
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
