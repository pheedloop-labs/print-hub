import { getState } from './api.js'

/* Polls the hub and holds the last good reading.
 *
 * Two things worth not undoing.
 *
 * It keeps the previous reading when a poll fails, and reports staleness
 * separately, rather than blanking the screen. A phone that loses venue wifi
 * for three seconds should not make every printer disappear; showing the
 * last known state with an honest "last seen" beats showing nothing.
 *
 * The browser polling slowly is fine, but it is NOT how jobs get recorded.
 * The whole print lifecycle is visible for roughly 1.4 s (CLAUDE.MD, Closed
 * task 4), so anything polling slower than about a second misses that a job
 * existed at all. The durable job record has to be written by the hub
 * itself, at ~0.5 s, not reconstructed from this. That is ENG-3783.
 */
export class HubState {
  data = $state(null)
  error = $state(null)
  loading = $state(true)
  lastOk = $state(null)

  #timer = null
  #interval

  constructor(interval = 2000) {
    this.#interval = interval
  }

  get printers() {
    return this.data?.printers ?? []
  }

  get hub() {
    return this.data?.hub ?? null
  }

  /** Seconds since the last successful poll, or null before the first. */
  get staleSeconds() {
    if (!this.lastOk) return null
    return Math.round((Date.now() - this.lastOk) / 1000)
  }

  async refresh() {
    try {
      this.data = await getState()
      this.lastOk = Date.now()
      this.error = null
    } catch (err) {
      // Keep this.data: the last good reading is more useful than a blank.
      this.error = err.message
    } finally {
      this.loading = false
    }
  }

  start() {
    this.refresh()
    this.#timer = setInterval(() => this.refresh(), this.#interval)
    return () => this.stop()
  }

  stop() {
    if (this.#timer) clearInterval(this.#timer)
    this.#timer = null
  }
}
