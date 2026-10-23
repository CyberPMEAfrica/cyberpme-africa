// Encode only the server-issued TOTP setup for the key shown beside the QR.
// Never send this URI to an external image/QR service or persistent storage.
export function mfaQrValue(setup) {
  if (typeof setup?.otpauth_uri !== 'string' || typeof setup?.secret !== 'string') return null;
  const value = setup.otpauth_uri;
  if (value.length > 2048 || value !== value.trim() || !/^[A-Z2-7]{16,128}$/.test(setup.secret)) return null;
  try {
    const uri = new URL(value);
    if (uri.protocol !== 'otpauth:' || uri.hostname !== 'totp' || uri.pathname.length < 2 || uri.hash || uri.username || uri.password || uri.port) return null;
    const expected = { secret: setup.secret, issuer: 'CyberPME', algorithm: 'SHA1', digits: '6', period: '30' };
    if (Object.entries(expected).some(([key, wanted]) => uri.searchParams.getAll(key).length !== 1 || uri.searchParams.get(key) !== wanted)) return null;
    return value;
  } catch {
    return null;
  }
}
