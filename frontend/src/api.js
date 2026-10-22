// The deployed web UI talks only to its own origin. Vercel proxies /api to the
// backend so HttpOnly cookies are first-party, not third-party cookies.
export const API_URL = import.meta.env.DEV
  ? (import.meta.env.VITE_API_URL || window.location.origin).replace(/\/$/, '')
  : window.location.origin;

export function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers);
  headers.delete('Authorization');
  headers.set('X-CyberPME-Browser', '1');
  return window.fetch(url, { ...options, headers, credentials: 'include' });
}
