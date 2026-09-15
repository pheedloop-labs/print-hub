<script>
  import QueueTable from '../components/QueueTable.svelte'
  import { go } from '../lib/router.svelte.js'

  let { hub } = $props()

  // Flatten every printer's in-flight jobs into one list, tagged with whose
  // they are. This is the venue question: is anything waiting, anywhere?
  let rows = $derived(
    hub.printers.flatMap((p) =>
      (p.jobs ?? []).map((j) => ({ ...j, printer: p.name, queue: p.queue }))
    )
  )

  // A queue that is paused or faulted will hold whatever is sent to it, so
  // it is worth naming even when nothing is queued behind it yet.
  let blocked = $derived(
    hub.printers.filter((p) => p.state === 'paused' || p.state === 'fault')
  )
</script>

<section>
  <div class="head">
    <h2>Spooler</h2>
    <p class="count">{rows.length} in flight across {hub.printers.length} queues</p>
  </div>

  {#if blocked.length}
    <div class="blocked">
      <p class="title">These queues will hold anything sent to them</p>
      <ul>
        {#each blocked as p}
          <li>
            <button class="link" onclick={() => go('printers', p.queue)}>{p.name}</button>
            — {p.detail}
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  <QueueTable {rows} showPrinter={true} />

  <p class="caveat">
    This is the live spooler, not a history — see Jobs for what the hub was
    asked to print. A job is normally here for about a second and a half, so
    an empty list is the healthy resting state and proves nothing either way.
    Anything sitting here for more than a few seconds is being held.
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
  }

  .blocked {
    background: rgb(var(--state-warn-bg));
    border: 1px solid rgb(var(--state-warn-fg) / 0.3);
    border-radius: var(--rounded-m);
    padding: var(--sp-xs) var(--sp-s);
    margin-bottom: var(--sp-s);
    color: rgb(var(--state-warn-fg));
  }

  .blocked .title {
    margin: 0 0 var(--sp-xxs);
    font-weight: var(--font-semibold);
    font-size: var(--font-size-sm);
  }

  .blocked ul {
    margin: 0;
    padding-left: var(--sp-s);
    font-size: var(--font-size-sm);
    line-height: var(--line-height-lg);
  }

  .link {
    font: inherit;
    font-weight: var(--font-medium);
    color: inherit;
    background: none;
    border: none;
    padding: 0;
    text-decoration: underline;
    cursor: pointer;
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
