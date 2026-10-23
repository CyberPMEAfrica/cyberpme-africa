// Local fixture only. The secret and password below are synthetic test data.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(process.env.CYBERPME_PLAYWRIGHT_PATH || 'playwright');

(async () => {
  const base = 'http://127.0.0.1:5182';
  const secret = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP';
  const uri = `otpauth://totp/CyberPME%3Apme-test%3Aowner%40example.test?secret=${secret}&issuer=CyberPME&algorithm=SHA1&digits=6&period=30`;
  const out = path.resolve(__dirname, '../../tmp/mfa-qr-check');
  await fs.mkdir(out, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.CYBERPME_BROWSER_PATH || undefined, headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  let authenticated = true;
  let invalidSetup = false;
  let setupCalls = 0;
  const errors = [];
  const leaks = [];
  await context.addInitScript({ path: path.resolve(__dirname, '../node_modules/jsqr/dist/jsQR.js') });
  await context.route('**/*', route => {
    const request = route.request();
    if (request.url().includes(secret) || (request.postData() || '').includes(secret)) leaks.push('secret transmitted in request');
    if (new URL(request.url()).origin !== base) return route.abort();
    return route.continue();
  });
  await context.route('**/api/v1/**', route => {
    const request = route.request();
    if (request.url().includes(secret) || (request.postData() || '').includes(secret)) leaks.push('secret transmitted in API request');
    const pathname = new URL(request.url()).pathname;
    let status = 200;
    let payload = [];
    if (pathname.endsWith('/auth/me')) {
      status = authenticated ? 200 : 401;
      payload = { email: 'owner@example.test', role: 'owner', theme: 'dark', mfa_setup_required: true };
    } else if (pathname.endsWith('/auth/mfa/status')) payload = { enabled: false, recovery_codes_remaining: 0 };
    else if (pathname.endsWith('/auth/mfa/setup')) {
      setupCalls++;
      payload = { secret, otpauth_uri: invalidSetup ? 'invalid-setup-for-fallback-test' : uri };
    } else if (pathname.endsWith('/auth/mfa/enable')) {
      assert.equal(request.postDataJSON().code, '123456');
      authenticated = false;
      payload = { recovery_codes: Array.from({ length: 10 }, (_, i) => 'synthetic-recovery-' + i) };
    }
    return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.text().includes(secret)) leaks.push('secret in console'); });
  const qr = () => page.getByRole('img', { name: 'QR code de configuration MFA CyberPME' });
  async function decodeVisibleQr() {
    const png = await page.locator('.mfa-qr-frame').screenshot();
    const decoded = await page.evaluate(async data => {
      const image = new Image();
      image.src = data;
      await image.decode();
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(image, 0, 0);
      const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
      return window.jsQR(pixels.data, canvas.width, canvas.height)?.data;
    }, 'data:image/png;base64,' + png.toString('base64'));
    assert.equal(decoded, uri, 'Visible QR must decode to the exact server-issued TOTP URI');
  }
  async function prepare() {
    await page.getByRole('heading', { name: 'Sécuriser votre compte' }).waitFor();
    assert.equal(await qr().count(), 0, 'No QR before password-confirmed setup');
    await page.getByLabel('Mot de passe actuel', { exact: true }).fill('Synthetic-password-for-browser-test');
    await page.getByRole('button', { name: 'Préparer la MFA', exact: true }).click();
  }
  try {
    await page.goto(base);
    await prepare();
    await qr().waitFor();
    assert.equal(await page.getByLabel('Clé à saisir dans l’application').inputValue(), secret);
    for (const theme of ['dark', 'light', 'black']) {
      await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
      await decodeVisibleQr();
    }
    await page.screenshot({ path: path.join(out, 'desktop.png'), fullPage: true });
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'No mobile horizontal overflow');
      await decodeVisibleQr();
    }
    await page.screenshot({ path: path.join(out, 'mobile.png'), fullPage: true });
    assert.equal(setupCalls, 1);
    await page.getByLabel('Code actuel', { exact: true }).fill('123456');
    await page.getByRole('button', { name: 'Activer et recevoir les codes de secours' }).click();
    await page.getByRole('button', { name: 'Codes sauvegardés — me reconnecter' }).waitFor();
    assert.equal(await qr().count(), 0, 'QR removed after activation');
    assert.equal(await page.getByLabel('Clé à saisir dans l’application').count(), 0);
    const stored = await page.evaluate(() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)]));
    assert(!stored.includes(secret) && !stored.includes('otpauth:'), 'No setup secret persisted in browser storage');
    // A malformed/older setup response must not crash the enrollment screen.
    authenticated = true; invalidSetup = true;
    await page.reload();
    await prepare();
    await page.getByText('QR code indisponible. Vous pouvez utiliser la clé manuelle ci-dessous.').waitFor();
    assert.equal(await page.getByLabel('Clé à saisir dans l’application').inputValue(), secret);
    assert.deepEqual(leaks, []);
    assert.deepEqual(errors, []);
    console.log('PASS: QR decoded in 3 themes and at mobile widths 390/320; manual key identical; no third-party secret transmission; QR removed after activation; no browser storage; manual fallback works.');
  } finally {
    await context.close();
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exit(1); });
