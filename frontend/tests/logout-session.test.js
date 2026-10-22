import { test } from 'node:test';
import assert from 'node:assert/strict';
import { revokeBrowserSession } from '../src/logout-session.js';

test('logout sends a cancellable POST and accepts server confirmation', async () => {
  await revokeBrowserSession(async (url, options) => {
    assert.equal(url, '/logout');
    assert.equal(options.method, 'POST');
    assert(options.signal instanceof AbortSignal);
    return { ok: true, status: 204 };
  }, '/logout');
});

test('an expired or already-revoked session is signed out', async () => {
  await revokeBrowserSession(async () => ({ ok: false, status: 401 }), '/logout');
});

test('server errors and CSRF rejection do not claim successful revocation', async () => {
  for (const status of [403, 500, 503]) {
    await assert.rejects(revokeBrowserSession(async () => ({ ok: false, status }), '/logout'));
  }
});

test('network failure is reported', async () => {
  await assert.rejects(revokeBrowserSession(async () => { throw new TypeError('Offline'); }, '/logout'));
});

test('a hanging server is bounded even if the transport ignores abort', async () => {
  let signal;
  await assert.rejects(revokeBrowserSession((url, options) => {
    signal = options.signal;
    return new Promise(() => {});
  }, '/logout', { timeoutMs: 15 }));
  assert.equal(signal.aborted, true);
});
