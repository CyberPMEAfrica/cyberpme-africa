import { defineConfig } from 'vite';

export default defineConfig({
  define: { __AGENT_RELEASE_COMMIT__: JSON.stringify(process.env.VERCEL_GIT_COMMIT_SHA || process.env.CYBERPME_AGENT_REVISION || '') },
  server: { host: '127.0.0.1', proxy: { '/api': 'http://127.0.0.1:8000' } },
});
