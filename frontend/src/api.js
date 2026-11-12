const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

async function getJson(path) {
  const response = await fetch(`${API_URL}${path}`);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.detail || `Request to ${path} failed (${response.status})`);
  }
  return body;
}

async function postJson(path, payload = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(body?.detail || `Request to ${path} failed (${response.status})`);
  }
  return body;
}

export function checkHealth() {
  return getJson('/health');
}

export function checkDatabase() {
  return getJson('/health/db');
}

export async function getReadingCount() {
  const body = await getJson('/stats/reading-count');
  return body.count;
}

export function listSites() {
  return getJson('/analytics/sites?site_type=household');
}

export function getSiteSummary(siteId) {
  return getJson(`/analytics/site-summary/${siteId}`);
}

export function getRanking(siteId, period = 'day') {
  return getJson(`/analytics/ranking?site_id=${siteId}&period=${period}`);
}

export function getDeviceDailySummary(deviceId) {
  return getJson(`/analytics/daily-summary/${deviceId}`);
}

export function getComparison(siteId, period = 'day') {
  return getJson(`/analytics/comparison/${siteId}?period=${period}`);
}

export function getHeatmap(siteId) {
  return getJson(`/analytics/heatmap/${siteId}`);
}

export function getIntervalReadings(siteId, date) {
  return getJson(`/analytics/interval/${siteId}?date=${date}`);
}

// "Simulate Community Day" button: streams one simulated day for every
// household (or a chosen subset) at a presentable pace, with the backend
// periodically recomputing summaries/comparisons as it goes.
export function startSimulation(opts = {}) {
  return postJson('/demo/start', opts);
}

export function getSimulationStatus() {
  return getJson('/demo/status');
}

export function stopSimulation() {
  return postJson('/demo/stop');
}

export { API_URL };
