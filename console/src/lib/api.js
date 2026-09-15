/* Thin wrapper over the hub's HTTP API.
 *
 * In dev these go to Vite on :5173 and are proxied to the hub on :8080.
 * In production the console is served by the hub itself, so they are
 * same-origin. Nothing here needs to know which.
 */

async function get(path) {
  const res = await fetch(path, { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`${path} returned HTTP ${res.status}`)
  return res.json()
}

/** Hub health plus one reading per printer. The console's main poll. */
export function getState() {
  return get('/api/state')
}

/** Every queue the hub process can see, usable or not. */
export function getPrinters() {
  return get('/printers')
}
