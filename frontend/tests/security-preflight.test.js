import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateReadiness } from '../security-preflight.mjs';

test('release rejects legacy or missing backend capability marker', () => {
  for (const value of [null, {}, { protocol: 'legacy' }, { status: 'ok' }]) {
    assert.throws(() => validateReadiness(value));
  }
});

test('release accepts the expected protected-session protocol', () => {
  assert.doesNotThrow(() => validateReadiness({ protocol: 'cyberpme-cookie-mfa-v1' }));
});
