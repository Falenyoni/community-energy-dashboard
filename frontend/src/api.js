const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

async function getJson(path) {
  const response = await fetch(`${API_URL}${path}`);
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

export { API_URL };
