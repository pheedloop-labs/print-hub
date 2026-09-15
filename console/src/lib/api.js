/* Thin wrapper over the hub's HTTP API.
 *
 * In dev these go to Vite on :5173 and are proxied to the hub on :8080.
 * In production the console is served by the hub itself, so they are
 * same-origin. Nothing here needs to know which.
 */

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { Accept: 'application/json' },
    ...options,
  })
  let body = null
  try {
    body = await res.json()
  } catch {
    body = null
  }
  if (!res.ok) {
    const err = new Error(body?.error || `${path} returned HTTP ${res.status}`)
    err.body = body
    throw err
  }
  return body
}

/** Hub health plus one reading per printer. The console's main poll. */
export function getState() {
  return request('/api/state')
}

/** The job record. Not the live queue — see printhub/journal.py. */
export function getJobs(limit = 50) {
  return request(`/api/jobs?limit=${limit}`)
}

/** Send a printer its own calibration card. Spends real media. */
export function sendTestPage(queue) {
  return request(`/api/test-page?queue=${encodeURIComponent(queue)}`, {
    method: 'POST',
  })
}

/* The OnSite app's own API, read here so the Connect page shows exactly what
 * the app will see rather than a second description of it. */

/** Hub identity, address and the endpoint list. */
export function getHub() {
  return request('/api/v1/hub')
}

/** Printers as the app sees them: ids, names, and whether they accept. */
export function getAppPrinters() {
  return request('/api/v1/printers')
}
