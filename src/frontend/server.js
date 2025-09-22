// server.js
const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const next = require('next');

const dev = process.env.NODE_ENV !== 'production';
const app = next({ dev });
const handle = app.getRequestHandler();

const PORT = process.env.PORT || 3000;
const BOA_TARGET = process.env.BOA_TARGET || 'http://frontend.boa.svc.cluster.local'; // BoA Flask svc

async function main() {
  await app.prepare();
  const server = express();

  // --- Health check (good for GKE readiness/liveness)
  server.get('/healthz', (_req, res) => res.status(200).send('ok'));

  // --- ONLY proxy the exact paths you need ---

  // 1) Proxy BoA under /bank/* so your popup can hit /bank/login via the same ingress
  server.use(
    '/bank',
    createProxyMiddleware({
      target: BOA_TARGET,
      changeOrigin: true,
      xfwd: true,
      // Needed for path-prefix preservation. We want /bank/login -> target:/login
      pathRewrite: { '^/bank': '' },
      // (Optional) timeouts
      proxyTimeout: 10000,
      timeout: 10000,
    })
  );

  // 2) If you have a backend engine and you **want** to proxy *just this one* endpoint:
  // server.use(
  //   '/api/game-state',
  //   createProxyMiddleware({
  //     target: 'http://save2win-engine.boa.svc.cluster.local', // your engine svc
  //     changeOrigin: true,
  //     xfwd: true,
  //   })
  // );

  // --- Everything else, including Next App Router **API routes** like /api/oauth ---
  // Let Next handle it! This is the crucial bit that keeps /api/oauth working.
  server.all('*', (req, res) => handle(req, res));

  server.listen(PORT, () => {
    console.log(`> Custom server ready on http://0.0.0.0:${PORT}`);
    console.log(`> Proxying /bank/* -> ${BOA_TARGET}`);
  });
}

main().catch((err) => {
  console.error('Fatal error in server.js:', err);
  process.exit(1);
});
