<script>
  import StatusPill from './StatusPill.svelte'

  let { printer } = $props()

  // Faults the driver named, plus whatever the job or pStatus carried. The
  // three sources disagree about where the truth lives, so show which one
  // spoke rather than flattening them into one line (Verified 50).
  let named = $derived(printer.printer_faults ?? [])
  let jobFlags = $derived(
    (printer.job_faults ?? []).filter((f) => f !== 'RETAINED' && f !== 'PRINTING')
  )
</script>

<article
  class="card"
  class:alert={printer.state === 'fault' || printer.state === 'unreachable'}
  class:warn={printer.state === 'offline' || printer.state === 'stalled'}
>
  <header>
    <div class="id">
      <h3>{printer.name}</h3>
      <p class="queue mono">{printer.queue}</p>
    </div>
    <StatusPill state={printer.state} />
  </header>

  {#if printer.detail}
    <p class="detail">{printer.detail}</p>
  {/if}

  {#if named.length || jobFlags.length || printer.pstatus}
    <ul class="sources">
      {#each named as f}
        <li><span class="src">printer</span> <code>{f.code}</code> {f.text}</li>
      {/each}
      {#if jobFlags.length}
        <li><span class="src">job</span> <code>{jobFlags.join(' | ')}</code></li>
      {/if}
      {#if printer.pstatus}
        <li><span class="src">pStatus</span> {printer.pstatus}</li>
      {/if}
    </ul>
  {/if}

  <footer>
    <span>{printer.driver ?? 'driver unknown'}</span>
    <span class="sep">·</span>
    <span class="mono">{printer.port ?? '?'}</span>
    {#if printer.jobs_queued > 0}
      <span class="sep">·</span>
      <span>{printer.jobs_queued} queued</span>
    {/if}
  </footer>
</article>

<style>
  .card {
    background: rgb(var(--surface-contrast));
    border: 1px solid rgb(var(--border-neutral-light));
    border-radius: var(--rounded-l);
    padding: var(--sp-s);
    box-shadow: var(--shadow);
    display: flex;
    flex-direction: column;
    gap: var(--sp-xs);
  }

  .alert {
    border-color: rgb(var(--state-fault-fg) / 0.45);
  }

  .warn {
    border-color: rgb(var(--state-warn-fg) / 0.45);
  }

  header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--sp-xs);
  }

  .id {
    min-width: 0;
  }

  h3 {
    font-size: var(--font-size-lg);
    line-height: var(--line-height-lg);
    overflow-wrap: anywhere;
  }

  .queue {
    margin: 2px 0 0;
    color: rgb(var(--text-caption));
    overflow-wrap: anywhere;
  }

  .detail {
    margin: 0;
    color: rgb(var(--text-caption));
    font-size: var(--font-size-sm);
    line-height: var(--line-height-sm);
  }

  .sources {
    margin: 0;
    padding: var(--sp-xs);
    list-style: none;
    background: rgb(var(--surface-neutral));
    border-radius: var(--rounded-m);
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: var(--font-size-sm);
    line-height: var(--line-height-sm);
  }

  .sources li {
    overflow-wrap: anywhere;
  }

  .src {
    display: inline-block;
    min-width: 54px;
    color: rgb(var(--text-subtle));
    font-size: var(--font-size-xs);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  code {
    font-family: var(--mono);
    background: rgb(var(--surface-muted));
    border-radius: var(--rounded-s);
    padding: 0 5px;
  }

  footer {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    color: rgb(var(--text-subtle));
    font-size: var(--font-size-sm);
    line-height: var(--line-height-sm);
    border-top: 1px solid rgb(var(--border-neutral-light));
    padding-top: var(--sp-xxs);
  }

  .sep {
    opacity: 0.5;
  }
</style>
