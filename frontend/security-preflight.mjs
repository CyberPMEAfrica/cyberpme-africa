import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

export function validateReadiness(payload) {
  if (payload?.protocol !== 'cyberpme-cookie-mfa-v1') {
    throw new Error('API incompatible : publier le backend sécurisé avant le frontend.');
  }
}

async function main() {
  if (process.env.VERCEL_ENV !== 'production') return;
  const config = JSON.parse(await readFile(new URL('./vercel.json', import.meta.url), 'utf8'));
  const destination = config.rewrites?.find(rule => rule.source === '/api/:path*')?.destination;
  if (!destination) throw new Error('Proxy API de production non configuré.');
  const api = new URL(destination);
  if (api.protocol !== 'https:') throw new Error('Le proxy de production exige HTTPS.');
  const response = await fetch(new URL('/api/v1/security/readiness', api.origin), { redirect: 'error', signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error('Backend sécurisé non prêt. Le frontend actuel est conservé ; publier l’API, puis relancer ce build.');
  validateReadiness(await response.json());
  console.log('Backend compatible avec les sessions protégées.');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
