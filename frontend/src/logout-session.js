// This flag contains no credential. It prevents a reload from reopening a cookie
// session while its server-side revocation is still unconfirmed.
export const LOGOUT_PENDING_KEY = 'cyberpme_logout_pending';

export async function revokeBrowserSession(request, url, { timeoutMs = 8000 } = {}) {
  const controller = new AbortController();
  let timer;
  try {
    const response = await Promise.race([
      request(url, { method: 'POST', signal: controller.signal }),
      new Promise((_, reject) => {
        timer = setTimeout(() => {
          controller.abort();
          reject(new Error('Logout timed out'));
        }, timeoutMs);
      }),
    ]);
    // An expired or already-revoked session is also safely signed out.
    if (!response.ok && response.status !== 401) throw new Error('Logout not confirmed');
  } finally {
    clearTimeout(timer);
  }
}
