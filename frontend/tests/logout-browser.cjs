// Run against a local Vite preview only. All API traffic is mocked: no account,
// production session or server infrastructure is used by this regression test.
// Requires Playwright (or PLAYWRIGHT_MODULE) and a browser (or BROWSER_EXE).
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_EXE ? { executablePath: process.env.BROWSER_EXE } : {}) });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  let logoutMode = 'held', releaseLogout, holdSync = false, releaseSync;
  let dataRequests = 0, meRequests = 0, loginRequests = 0;
  const user = { email: 'logout@example.test', role: 'owner', organization_name: 'Test isolé', theme: 'dark' };
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route('**/api/v1/**', async route => {
    const endpoint = new URL(route.request().url()).pathname;
    if (endpoint.endsWith('/auth/logout')) {
      if (logoutMode === 'held') await new Promise(resolve => { releaseLogout = resolve; });
      if (logoutMode === 'hanging') return;
      if (logoutMode === 'offline') return route.abort('internetdisconnected');
      if (logoutMode === 'failure') return route.fulfill({ status: 503, json: {} });
      return route.fulfill({ status: 204 });
    }
    if (endpoint.endsWith('/auth/me')) { meRequests++; return route.fulfill({ json: user }); }
    if (endpoint.endsWith('/auth/login')) { loginRequests++; return route.fulfill({ json: {} }); }
    dataRequests++;
    if (holdSync && endpoint.endsWith('/servers')) await new Promise(resolve => { releaseSync = resolve; });
    return route.fulfill({ json: [] }).catch(() => {}); // Pending sync may have been cancelled.
  });
  const loginHeading = () => page.getByRole('heading', { name: 'Connexion', exact: true });
  async function openDashboard() {
    await page.goto('http://127.0.0.1:5179');
    await page.getByRole('heading', { name: 'Vue d’ensemble', exact: true }).waitFor();
    await page.locator('.refresh-button[aria-busy="false"]').waitFor();
  }
  async function clickLogout() {
    await page.getByRole('button', { name: 'Ouvrir le menu du compte' }).click();
    await page.getByRole('menuitem', { name: 'Se déconnecter' }).click();
    await loginHeading().waitFor({ timeout: 1500 });
    assert.equal(await page.locator('.app-shell').count(), 0);
  }
  try {
    await openDashboard();
    holdSync = true;
    await page.getByRole('button', { name: 'Actualiser les données' }).click();
    await page.waitForFunction(() => document.querySelector('.refresh-button')?.getAttribute('aria-busy') === 'true');
    await clickLogout();
    await page.getByText('Espace fermé. Confirmation de la déconnexion en cours…', { exact: true }).waitFor();
    assert(await page.getByRole('button', { name: 'Se connecter', exact: true }).isDisabled());
    releaseSync?.(); holdSync = false;
    const count = dataRequests;
    // Past the 10-second auto-refresh interval, no protected polling may remain.
    await page.waitForTimeout(11000);
    assert.equal(dataRequests, count);
    await page.getByRole('button', { name: 'Réessayer la déconnexion' }).waitFor();
    // A late response must not restore the dashboard or enable login.
    releaseLogout();
    assert(await loginHeading().isVisible());
    assert(await page.getByRole('button', { name: 'Se connecter', exact: true }).isDisabled());

    logoutMode = 'failure';
    const meBeforeReload = meRequests;
    await page.reload();
    await page.getByRole('button', { name: 'Réessayer la déconnexion' }).waitFor();
    assert.equal(meRequests, meBeforeReload, 'A reload cannot reopen an unconfirmed cookie session');
    assert.equal(await page.evaluate(() => sessionStorage.getItem('cyberpme_logout_pending')), '1');
    await page.evaluate(() => { location.hash = '/invite?token=isolated-test'; });
    assert(await loginHeading().isVisible(), 'Invitation navigation cannot bypass pending logout');
    await page.evaluate(() => { location.hash = '/overview'; });
    logoutMode = 'offline';
    await page.getByRole('button', { name: 'Réessayer la déconnexion' }).click();
    await page.getByRole('button', { name: 'Réessayer la déconnexion' }).waitFor();
    assert.equal(loginRequests, 0);
    logoutMode = 'success';
    await page.getByRole('button', { name: 'Réessayer la déconnexion' }).click();
    await page.getByText('Vous êtes déconnecté.', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => sessionStorage.getItem('cyberpme_logout_pending')), null);
    assert.equal(await page.getByRole('button', { name: 'Se connecter', exact: true }).isDisabled(), false);
    // Normal quick logout also returns to login without any page reload.
    await openDashboard();
    await clickLogout();
    await page.getByText('Vous êtes déconnecté.', { exact: true }).waitFor();
    assert.deepEqual(errors, []);
    console.log('PASS: immediate logout, cancelled in-flight sync, no automatic polling after logout, bounded timeout, late response ignored, reload protection, server/offline failure and retry, normal logout; no rendering errors.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
