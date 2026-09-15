/* A hash router, in about thirty lines.
 *
 * Hash rather than history: the console is served by Flask from a static
 * folder, and a real path would 404 on refresh unless every route were also
 * a server route. Hashes need nothing from the server.
 *
 * Routes:
 *   #/printers                  the grid
 *   #/printers/<queue>          one printer, encoded
 *   #/queue                     everything in every spooler right now
 *   #/jobs                      the job record
 *   #/jobs/<queue>              the job record for one printer
 *
 * Queue names contain spaces and parentheses ("EPSON CW-C4000u (Copy 1)"),
 * so the segment is always encodeURIComponent'd and decoded on the way out.
 */

const DEFAULT = '/printers'

export class Router {
  path = $state(DEFAULT)

  constructor() {
    this.#read()
    window.addEventListener('hashchange', () => this.#read())
  }

  #read() {
    this.path = window.location.hash.slice(1) || DEFAULT
  }

  /** Decoded path segments: ['printers', 'EPSON CW-C4000u (Copy 1)'] */
  get parts() {
    return this.path
      .split('/')
      .filter(Boolean)
      .map((s) => {
        try {
          return decodeURIComponent(s)
        } catch {
          return s
        }
      })
  }

  get view() {
    return this.parts[0] ?? 'printers'
  }

  /** The queue this route is scoped to, or null for the global view. */
  get queue() {
    return this.parts[1] ?? null
  }
}

/** Navigate. Always encode the queue: it may contain spaces and brackets. */
export function go(view, queue = null) {
  window.location.hash = queue
    ? `/${view}/${encodeURIComponent(queue)}`
    : `/${view}`
}
