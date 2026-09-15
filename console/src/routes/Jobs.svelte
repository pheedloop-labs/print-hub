<script>
  let { hub } = $props()

  /* Deliberately small vocabulary. None of these is "printed": nothing in
   * the print path can confirm a badge physically exists. */
  const LABELS = {
    accepted: 'Accepted',
    sent: 'Sent to the spooler',
    spooled: 'Spooled',
    cleared: 'Left the queue',
    fault: 'Fault',
    failed: 'Failed',
  }

  function when(iso) {
    if (!iso) return ''
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }
</script>

<section>
  <div class="head">
    <h2>Jobs</h2>
    <p class="count">{hub.jobs.length} recorded</p>
  </div>

  {#if hub.jobs.length === 0}
    <p class="empty">
      Nothing recorded yet. Send a test page from the Printers view and it will
      appear here.
    </p>
  {:else}
    <ol class="list">
      {#each hub.jobs as job (job.job_id)}
        <li class="job {job.state}">
          <div class="row">
            <span class="state">{LABELS[job.state] ?? job.state}</span>
            <span class="target">{job.label ?? job.queue}</span>
            <span class="time mono">{when(job.last_seen)}</span>
          </div>
          <p class="id mono">{job.job_id}</p>
          {#if job.detail}<p class="detail">{job.detail}</p>{/if}
          {#if job.geometry}
            <p class="geo mono">
              {job.geometry.dpi} dpi · {job.geometry.raster_mm?.join(' × ')} mm
              {#if job.geometry.clipped}· <strong>CLIPPED</strong>{/if}
              {#if !job.geometry.scale_pinned}· <strong>not pinned</strong>{/if}
            </p>
          {/if}
          <p class="trail mono">
            {#each job.events as e, i}{#if i}&nbsp;→&nbsp;{/if}{e.event}{/each}
          </p>
        </li>
      {/each}
    </ol>
  {/if}

  <p class="caveat">
    This is the record of what the hub was asked to print, not the live queue —
    a job is in the spooler for about 1.4 seconds, which is faster than anyone
    can watch. <strong>No entry here ever says printed.</strong> "Left the
    queue" means the spooler released the job, which happens whether or not
    media emerged: nothing in the print path can confirm a badge physically
    exists.
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

  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--sp-xxs);
  }

  .job {
    background: rgb(var(--surface-contrast));
    border: 1px solid rgb(var(--border-neutral-light));
    border-left-width: 3px;
    border-radius: var(--rounded-m);
    padding: var(--sp-xs) var(--sp-s);
  }

  .job.fault,
  .job.failed {
    border-left-color: rgb(var(--state-fault-fg));
  }
  .job.cleared {
    border-left-color: rgb(var(--border-neutral));
  }
  .job.spooled,
  .job.sent,
  .job.accepted {
    border-left-color: rgb(var(--state-printing-fg));
  }

  .row {
    display: flex;
    align-items: baseline;
    gap: var(--sp-xs);
    flex-wrap: wrap;
  }

  .state {
    font-weight: var(--font-semibold);
    color: rgb(var(--text-heading));
  }

  .job.fault .state,
  .job.failed .state {
    color: rgb(var(--state-fault-fg));
  }

  .target {
    color: rgb(var(--text-body));
  }

  .time {
    margin-left: auto;
    color: rgb(var(--text-subtle));
  }

  .id,
  .detail,
  .geo,
  .trail {
    margin: 2px 0 0;
    font-size: var(--font-size-sm);
    line-height: var(--line-height-sm);
    overflow-wrap: anywhere;
  }

  .id {
    color: rgb(var(--text-subtle));
  }

  .detail {
    color: rgb(var(--text-caption));
  }

  .geo {
    color: rgb(var(--text-caption));
  }

  .geo strong {
    color: rgb(var(--state-fault-fg));
  }

  .trail {
    color: rgb(var(--text-subtle));
    font-size: var(--font-size-xs);
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
</style>
