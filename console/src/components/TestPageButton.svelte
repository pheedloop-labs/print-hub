<script>
  import { sendTestPage } from '../lib/api.js'

  let { printer, block = false } = $props()

  let sending = $state(false)
  let result = $state(null)

  /* A test page is the only way to find out whether a printer is well: no
   * fault is visible while a queue is idle (Verified 29). It also spends real
   * media, so it confirms first and is never automatic.
   *
   * The warning differs for a printer that is already reported offline or
   * paused, because those jobs report success whether or not anything comes
   * out - which is the failure mode this whole project keeps meeting.
   */
  async function send() {
    // Confirm only when media is actually at risk. An offline printer will
    // be refused by the hub, so there is nothing to warn about - clicking
    // just surfaces the reason. A paused one holds the job rather than
    // losing it, which is worth saying but is not a refusal.
    if (printer.state !== 'offline') {
      const warning =
        printer.state === 'paused'
          ? `${printer.name} is paused, so the job will wait in the queue rather than print now. Send it anyway?`
          : `Send a calibration card to ${printer.name}? This uses real media.`
      if (!window.confirm(warning)) return
    }

    sending = true
    result = null
    try {
      const r = await sendTestPage(printer.queue)
      result = {
        ok: !r.clipped,
        text: r.clipped
          ? 'Sent, but the page does not fit the printable area'
          : 'Sent to the spooler. Watch Jobs for what followed.',
      }
    } catch (err) {
      const problems = err.body?.problems
      result = {
        ok: false,
        text: problems ? `${err.message}: ${problems.join('; ')}` : err.message,
      }
    } finally {
      sending = false
    }
  }
</script>

{#if result}
  <p class="result" class:bad={!result.ok}>{result.text}</p>
{/if}

<button class="test" class:block onclick={send} disabled={sending}>
  {sending ? 'Sending…' : 'Test page'}
</button>

<style>
  .test {
    font: inherit;
    font-size: var(--font-size-sm);
    font-weight: var(--font-medium);
    color: rgb(var(--text-primary));
    background: rgb(var(--surface-contrast));
    border: 1px solid rgb(var(--border-primary));
    border-radius: var(--rounded-s);
    padding: 3px var(--sp-xs);
    cursor: pointer;
  }

  .test:hover:not(:disabled) {
    background: rgb(var(--surface-primary-accent));
  }

  .test:disabled {
    color: rgb(var(--text-disabled));
    border-color: rgb(var(--border-neutral));
    cursor: default;
  }

  .block {
    padding: 6px var(--sp-s);
    font-size: var(--font-size-base);
  }

  .result {
    margin: 0 0 var(--sp-xxs);
    padding: var(--sp-xxs) var(--sp-xs);
    border-radius: var(--rounded-s);
    font-size: var(--font-size-sm);
    line-height: var(--line-height-sm);
    color: rgb(var(--state-printing-fg));
    background: rgb(var(--state-printing-bg));
    border: 1px solid rgb(var(--state-printing-fg) / 0.3);
  }

  .result.bad {
    color: rgb(var(--state-fault-fg));
    background: rgb(var(--state-fault-bg));
    border-color: rgb(var(--state-fault-fg) / 0.3);
  }
</style>
