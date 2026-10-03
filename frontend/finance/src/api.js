export async function fetchDashboardData() {
  const res = await fetch('/finance/api/data');
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.json();
}

export async function saveSpreadsheetUrl(spreadsheetUrl) {
  const res = await fetch('/finance/api/spreadsheet', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ spreadsheet_url: spreadsheetUrl }),
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.json();
}

// Throws on failure — the body (parsed as JSON when possible) carries
// `error`/`message` fields the caller can inspect, e.g. to special-case
// "insufficient_scope" (needs re-authorizing with write access) instead of
// showing a generic failure.
export async function saveSnapshot() {
  const res = await fetch('/finance/api/snapshot', { method: 'POST' });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || !body.ok) {
    const err = new Error(body.message || body.error || `Request failed: ${res.status}`);
    err.code = body.error;
    throw err;
  }
  return body;
}
