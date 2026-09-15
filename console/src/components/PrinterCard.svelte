<script>
  import StatusPill from './StatusPill.svelte'
  import TestPageButton from './TestPageButton.svelte'
  import { go } from '../lib/router.svelte.js'

  let { printer } = $props()

  // Faults the driver named, plus whatever the job or pStatus carried. The
  // three sources disagree about where the truth lives, so show which one
  // spoke rather than flattening them into one line (Verified 50).
  let named = $derived(printer.printer_faults ?? [])
  let jobFlags = $derived(
    (printer.job_faults ?? []).filter((f) => f !== 'RETAINED' && f !== 'PRINTING')
  )

  // Badges about the queue itself rather than its health. Ordered worst
  // first, because on a phone only the first line or two is read.
  let badges = $derived(
    [
      printer.configured && !printer.pinned
        ? {
            tone: 'bad',
            text: 'not pinned',
            title:
              'No captured DEVMODE blob, so jobs inherit whatever the driver UI was last set to. This has silently produced a 5% oversized card and an uncut badge.',
          }
        : null,
      printer.dialog_port
        ? {
            tone: 'bad',
            text: 'opens a dialog',
            title:
              'This queue prompts for a filename. A modal dialog on a machine with no screen is an outage - never print to it.',
          }
        : null,
      printer.duplicate_port
        ? {
            tone: 'warn',
            text: 'shares a port',
            title:
              'Another queue uses the same port. One of the pair may be an orphan: enumerable, identical in every public field, and not usable.',
          }
        : null,
      !printer.configured
        ? {
            tone: 'muted',
            text: 'not configured',
            title:
              'The hub can see this queue but has no card or blob for it, so it is not used.',
          }
        : null,
    ].filter(Boolean)
  )
</script>

<article
  class="card"
  class:alert={printer.state === 'fault' || printer.state === 'unreachable'}
  class:warn={printer.state === 'offline' || printer.state === 'stalled'}
  class:dim={!printer.configured}
>
  <header>
    <div class="id">
      <h3><button class="name" onclick={() => go('printers', printer.queue)}>{printer.name}</button></h3>
      <p class="queue mono">{printer.queue}</p>
    </div>
    <StatusPill state={printer.state} />
  </header>

  {#if badges.length}
    <div class="badges">
      {#each badges as b}
        <span class="badge {b.tone}" title={b.title}>{b.text}</span>
      {/each}
    </div>
  {/if}

  {#if printer.detail}
    <p class="detail">{printer.detail}</p>
  {/if}

  {#if named.length || jobFlags.length || printer.pstatus || printer.config_problems?.length}
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
      {#each printer.config_problems ?? [] as problem}
        <li><span class="src">config</span> {problem}</li>
      {/each}
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
    {#if printer.configured}
      <span class="spacer"></span>
      <TestPageButton {printer} />
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

  /* A queue the hub is not managing is still shown, because "what is on this
   * computer" is the question this list answers, but it recedes. */
  .dim {
    background: transparent;
    box-shadow: none;
    border-style: dashed;
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

  .badges {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .badge {
    font-size: var(--font-size-xs);
    line-height: var(--line-height-sm);
    font-weight: var(--font-medium);
    padding: 1px var(--sp-xxs);
    border-radius: var(--rounded-s);
    border: 1px solid transparent;
    cursor: help;
  }

  .badge.bad {
    color: rgb(var(--state-fault-fg));
    background: rgb(var(--state-fault-bg));
    border-color: rgb(var(--state-fault-fg) / 0.3);
  }

  .badge.warn {
    color: rgb(var(--state-warn-fg));
    background: rgb(var(--state-warn-bg));
    border-color: rgb(var(--state-warn-fg) / 0.3);
  }

  .badge.muted {
    color: rgb(var(--text-subtle));
    background: rgb(var(--surface-muted));
    border-color: rgb(var(--border-neutral));
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

  .spacer {
    margin-left: auto;
  }

  .name {
    font: inherit;
    color: inherit;
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    text-align: left;
  }

  .name:hover {
    color: rgb(var(--text-link));
    text-decoration: underline;
  }
</style>
