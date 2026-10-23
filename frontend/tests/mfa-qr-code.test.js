import assert from 'node:assert/strict';
import test from 'node:test';
import { mfaQrValue } from '../src/mfa-qr-code.js';

const secret = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP';
const uri = `otpauth://totp/CyberPME%3Apme-test%3Aowner%40example.test?secret=${secret}&issuer=CyberPME&algorithm=SHA1&digits=6&period=30`;
const setup = { secret, otpauth_uri: uri };

test('QR preserves the exact server-issued URI and the manual key', () => {
  assert.equal(mfaQrValue(setup), uri);
  assert.equal(new URL(mfaQrValue(setup)).searchParams.get('secret'), secret);
});

test('missing or malformed QR setup falls back to manual enrollment', () => {
  for (const value of [null, {}, { secret }, { ...setup, otpauth_uri: 'broken' }, { ...setup, otpauth_uri: null }]) {
    assert.equal(mfaQrValue(value), null);
  }
});

test('QR cannot enroll a different key or an external URL', () => {
  for (const value of [uri.replace(secret, 'A'.repeat(32)), uri.replace('otpauth://totp/', 'https://example.test/'), uri.replace('totp/', 'hotp/'), uri + '&secret=' + secret, uri + '#fragment']) {
    assert.equal(mfaQrValue({ ...setup, otpauth_uri: value }), null);
  }
});

test('QR parameters match the supported six-digit, 30-second CyberPME setup', () => {
  for (const [original, replacement] of [['issuer=CyberPME', 'issuer=Other'], ['algorithm=SHA1', 'algorithm=SHA256'], ['digits=6', 'digits=8'], ['period=30', 'period=60']]) {
    assert.equal(mfaQrValue({ ...setup, otpauth_uri: uri.replace(original, replacement) }), null);
  }
  assert.equal(mfaQrValue({ ...setup, otpauth_uri: uri + '&x=' + 'a'.repeat(2048) }), null);
});
