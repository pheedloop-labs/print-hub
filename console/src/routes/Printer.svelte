<script>
  import QueueTable from '../components/QueueTable.svelte'
  import StatusPill from '../components/StatusPill.svelte'
  import TestPageButton from '../components/TestPageButton.svelte'
  import { go } from '../lib/router.svelte.js'

  let { hub, queue } = $props()

  let printer = $derived(hub.printers.find((p) => p.queue === queue) ?? null)
  let jobs = $derived(hub.jobs.filter((j) => j.queue === queue))

  function when(iso) {
    if (!iso) return ''
    return new Date(iso).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }
</script>

<section>
  <button class="back" onclick={() => go('printers')}>← All printers</button>

  {#if !printer}
    <p class="empty">
      Windows is not reporting a queue called <code class="mono">{queue}</code>
      on this machine. It may have been removed, or renamed.
    </p>
  {:else}
    <header>
      <div>
        <h2>{printer.name}</h2>
        <p class="queue mono">{printer.queue}</p>
      </div>
      <StatusPill state={printer.state} />
    </header>

    {#if printer.detail}
      <p class="detail">{printer.detail}</p>
    {/if}

    <div class="panels">
      <div class="panel">
        <h3>In the spooler now</h3>
        <QueueTable rows={printer.jobs ?? []} />
      </div>

      <div class="panel">
        <h3>What the driver reports</h3>
        <dl>
          <dt>Driver</dt>
          <dd>{printer.driver ?? 'unknown'}</dd>
          <dt>Port</dt>
          <dd class="mono">{printer.port ?? '?'}</dd>
          <dt>Status word</dt>
          <dd class="mono">{printer.status}</dd>
          {#each printer.printer_faults ?? [] as f}
            <dt>Printer</dt>
            <dd class="bad"><code class="mono">{f.code}</code> {f.text}</dd>
          {/each}
          {#if printer.job_faults?.length}
            <dt>Job</dt>
            <dd class="mono">{printer.job_faults.join(' | ')}</dd>
          {/if}
          {#if printer.pstatus}
            <dt>pStatus</dt>
            <dd class="bad">{printer.pstatus}</dd>
          {/if}
        </dl>
        <p class="note">
          These three fields disagree about where a fault lives, and no two
          printers on this bench put it in the same one — so all three are
          shown rather than merged.
        </p>
      </div>

      <div class="panel">
        <h3>Configuration</h3>
        {#if !printer.configured}
          <p class="note">
            Not configured. The hub can see this queue but has no card or blob
            for it, so it will not print to it.
          </p>
        {:else}
          <dl>
            <dt>Scale</dt>
            <dd class={printer.pinned ? '' : 'bad'}>
              {printer.pinned
                ? 'Pinned to a captured blob'
                : 'NOT pinned — jobs inherit the driver UI'}
            </dd>
            {#if printer.note}
              <dt>Note</dt>
              <dd>{printer.note}</dd>
            {/if}
          </dl>
          {#each printer.config_problems ?? [] as problem}
            <p class="bad note">{problem}</p>
          {/each}
          <div class="actions">
            <TestPageButton {printer} block={true} />
          </div>
        {/if}
      </div>
    </div>

    <div class="history">
      <h3>Recent jobs on this printer</h3>
      {#if jobs.length === 0}
        <p class="note">Nothing recorded for this printer yet.</p>
      {:else}
        <ul class="jobs">
          {#each jobs as job (job.job_id)}
            <li class={job.state}>
              <span class="state">{job.state}</span>
              <span class="jid mono">{job.job_id}</span>
              <span class="time mono">{when(job.last_seen)}</span>
            </li>
          {/each}
        </ul>
      {/if}
      <button class="link" onclick={() => go('jobs')}>See the whole record →</button>
    </div>
  {/if}
</section>

<style>
  .back,
  .link {
    font: inherit;
    font-size: var(--font-size-sm);
    color: rgb(var(--text-link));
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
  }

  .back {
    margin-bottom: var(--sp-s);
  }

  header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--sp-s);
    flex-wrap: wrap;
    margin-bottom: var(--sp-xxs);
  }

  h2 {
    font-size: var(--font-size-2xl);
    line-height: var(--line-height-2xl);
  }

  h3 {
    font-size: var(--font-size-base);
    margin-bottom: var(--sp-xxs);
  }

  .queue {
    margin: 2px 0 0;
    color: rgb(var(--text-caption));
    overflow-wrap: anywhere;
  }

  .detail {
    margin: 0 0 var(--sp-s);
    color: rgb(var(--text-caption));
    font-size: var(--font-size-sm);
  }

  .panels {
    display: grid;
    gap: var(--sp-s);
    grid-template-columns: 1fr;
    margin-bottom: var(--sp-m);
  }

  @media (min-width: 760px) {
    .panels {
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    }
  }

  .panel,
  .history {
    background: rgb(var(--surface-contrast));
    border: 1px solid rgb(var(--border-neutral-light));
    border-radius: var(--rounded-l);
    padding: var(--sp-s);
  }

  dl {
    margin: 0;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px var(--sp-xs);
    font-size: var(--font-size-sm);
  }

  dt {
    color: rgb(var(--text-subtle));
    font-size: var(--font-size-xs);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding-top: 2px;
  }

  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }

  .bad {
    color: rgb(var(--state-fault-fg));
  }

  .note {
    margin: var(--sp-xxs) 0 0;
    color: rgb(var(--text-subtle));
    font-size: var(--font-size-xs);
    line-height: var(--line-height-sm);
  }

  .actions {
    margin-top: var(--sp-xs);
  }

  .jobs {
    list-style: none;
    margin: 0 0 var(--sp-xs);
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: var(--font-size-sm);
  }

  .jobs li {
    display: flex;
    gap: var(--sp-xs);
    align-items: baseline;
    padding: 3px 0;
    border-bottom: 1px solid rgb(var(--border-neutral-light));
  }

  .jobs .state {
    font-weight: var(--font-medium);
    min-width: 8ch;
  }

  .jobs li.fault .state,
  .jobs li.failed .state {
    color: rgb(var(--state-fault-fg));
  }

  .jid {
    color: rgb(var(--text-caption));
    overflow-wrap: anywhere;
  }

  .time {
    margin-left: auto;
    color: rgb(var(--text-subtle));
  }

  .empty {
    color: rgb(var(--text-caption));
    background: rgb(var(--surface-contrast));
    border: 1px dashed rgb(var(--border-neutral));
    border-radius: var(--rounded-l);
    padding: var(--sp-m);
    text-align: center;
  }
</style>
