<script>
  /* What is in the spooler right now, as opposed to what happened.
   *
   * Usually empty, and that is not a problem to apologise for: a job is in
   * the queue for roughly 1.4 seconds, so an empty queue is the normal
   * resting state and says nothing about whether the printer is well. A job
   * sitting here for more than a few seconds is the interesting case - it
   * means something is holding it.
   */
  let { rows = [], showPrinter = false } = $props()
</script>

{#if rows.length === 0}
  <p class="idle">
    Nothing in the spooler. Jobs pass through in about a second and a half, so
    this is usually empty even when printing is working.
  </p>
{:else}
  <ul class="rows">
    {#each rows as row (row.printer + ':' + row.id)}
      <li>
        <div class="line">
          {#if showPrinter}<span class="printer">{row.printer}</span>{/if}
          <span class="doc mono">{row.document ?? 'untitled'}</span>
          <span class="jid mono">#{row.id}</span>
        </div>
        {#if row.status_names?.length}
          <p class="flags mono">{row.status_names.join(' | ')}</p>
        {:else}
          <p class="flags quiet mono">no status bits set</p>
        {/if}
        {#if row.pstatus}
          <p class="pstatus">{row.pstatus}</p>
        {/if}
      </li>
    {/each}
  </ul>
{/if}

<style>
  .idle {
    margin: 0;
    color: rgb(var(--text-subtle));
    font-size: var(--font-size-sm);
    line-height: var(--line-height-lg);
  }

  .rows {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--sp-xxs);
  }

  .rows li {
    background: rgb(var(--surface-neutral));
    border-radius: var(--rounded-m);
    padding: var(--sp-xxs) var(--sp-xs);
  }

  .line {
    display: flex;
    align-items: baseline;
    gap: var(--sp-xs);
    flex-wrap: wrap;
  }

  .printer {
    font-weight: var(--font-medium);
    color: rgb(var(--text-heading));
  }

  .doc {
    color: rgb(var(--text-body));
    overflow-wrap: anywhere;
  }

  .jid {
    margin-left: auto;
    color: rgb(var(--text-subtle));
  }

  .flags,
  .pstatus {
    margin: 2px 0 0;
    font-size: var(--font-size-xs);
    line-height: var(--line-height-sm);
    color: rgb(var(--text-caption));
    overflow-wrap: anywhere;
  }

  /* A queued job with no status bits at all is the offline signature
   * (Verified 55), not an absence of information. */
  .quiet {
    color: rgb(var(--state-warn-fg));
  }

  .pstatus {
    color: rgb(var(--state-fault-fg));
  }
</style>
