<script>
  /* The one component that must not lie.
   *
   * There is no "Ready" and no green. Every fault a printer can have looks
   * healthy until a job is sent (CLAUDE.MD Verified 29), so the honest label
   * for a quiet queue is "No fault reported", in grey. ditto has a
   * success-green; a printer sitting still has not succeeded at anything. If
   * a future edit adds a green "Ready" here, it makes the console claim
   * something the hub has no way to know.
   */
  let { state = 'unknown', compact = false } = $props()

  const LABELS = {
    idle: 'No fault reported',
    printing: 'Printing',
    fault: 'Fault',
    stalled: 'Stalled',
    unreachable: 'Unreachable',
    unknown: 'Unknown',
  }
</script>

<span class="pill {state}" class:compact>
  <span class="dot"></span>
  {LABELS[state] ?? state}
</span>

<style>
  .pill {
    display: inline-flex;
    align-items: center;
    gap: var(--sp-xxs);
    padding: var(--sp-xxxs) var(--sp-xs) var(--sp-xxxs) var(--sp-xxs);
    border-radius: 999px;
    font-size: var(--font-size-sm);
    line-height: var(--line-height-sm);
    font-weight: var(--font-medium);
    white-space: nowrap;
    border: 1px solid transparent;
  }

  .compact {
    font-size: var(--font-size-xs);
    line-height: var(--line-height-xs);
    padding: 3px var(--sp-xxs) 3px 6px;
  }

  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex: none;
  }

  /* Grey, and a hollow dot. A quiet queue has not been shown to be well. */
  .idle {
    background: rgb(var(--state-idle-bg));
    color: rgb(var(--state-idle-fg));
    border-color: rgb(var(--state-idle-fg) / 0.2);
  }
  .idle .dot {
    background: transparent;
    box-shadow: inset 0 0 0 1.5px rgb(var(--state-idle-fg));
  }

  .printing {
    background: rgb(var(--state-printing-bg));
    color: rgb(var(--state-printing-fg));
    border-color: rgb(var(--state-printing-fg) / 0.28);
  }
  .printing .dot {
    background: rgb(var(--state-printing-fg));
    animation: pulse 1.4s ease-in-out infinite;
  }

  .fault,
  .unreachable {
    background: rgb(var(--state-fault-bg));
    color: rgb(var(--state-fault-fg));
    border-color: rgb(var(--state-fault-fg) / 0.3);
  }
  .fault .dot,
  .unreachable .dot {
    background: rgb(var(--state-fault-fg));
  }

  .stalled {
    background: rgb(var(--state-warn-bg));
    color: rgb(var(--state-warn-fg));
    border-color: rgb(var(--state-warn-fg) / 0.3);
  }
  .stalled .dot {
    background: rgb(var(--state-warn-fg));
  }

  .unknown {
    background: rgb(var(--surface-muted));
    color: rgb(var(--text-caption));
    border-color: rgb(var(--border-neutral));
  }
  .unknown .dot {
    background: rgb(var(--text-subtle));
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.35;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .printing .dot {
      animation: none;
    }
  }
</style>
