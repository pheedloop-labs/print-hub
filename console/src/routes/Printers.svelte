<script>
  import PrinterCard from '../components/PrinterCard.svelte'

  let { hub } = $props()

  let faulted = $derived(
    hub.printers.filter((p) => p.state === 'fault' || p.state === 'unreachable')
  )
</script>

<section>
  <div class="head">
    <h2>Printers</h2>
    <p class="count">
      {hub.printers.length} configured{#if faulted.length}, <strong
          >{faulted.length} reporting a fault</strong
        >{/if}
    </p>
  </div>

  {#if hub.loading}
    <p class="empty">Reading printers…</p>
  {:else if hub.printers.length === 0}
    <p class="empty">
      No printers configured. The hub reads its fleet from <code
        >printers.json</code
      >.
    </p>
  {:else}
    <div class="grid">
      {#each hub.printers as printer (printer.queue)}
        <PrinterCard {printer} />
      {/each}
    </div>
  {/if}

  <p class="caveat">
    A printer is never shown as ready. Every fault these printers can have —
    empty hopper, ribbon out, jam, cover open — reads as healthy until a job is
    actually sent, so a green light here would be a claim the hub cannot
    support. After a jam or ribbon change a printer takes 34–40 seconds to
    re-initialise, so a fault clearing slowly is normal.
  </p>
</section>

<style>
  .head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--sp-xs);
    flex-wrap: wrap;
    margin-bottom: var(--sp-s);
  }

  h2 {
    font-size: var(--font-size-xl);
    line-height: var(--line-height-xl);
  }

  .count {
    margin: 0;
    color: rgb(var(--text-caption));
    font-size: var(--font-size-sm);
    line-height: var(--line-height-sm);
  }

  .count strong {
    color: rgb(var(--state-fault-fg));
    font-weight: var(--font-semibold);
  }

  .grid {
    display: grid;
    gap: var(--sp-s);
    grid-template-columns: 1fr;
  }

  @media (min-width: 680px) {
    .grid {
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    }
  }

  .empty {
    color: rgb(var(--text-caption));
    background: rgb(var(--surface-contrast));
    border: 1px dashed rgb(var(--border-neutral));
    border-radius: var(--rounded-l);
    padding: var(--sp-m);
    text-align: center;
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

  code {
    font-family: var(--mono);
  }
</style>
