// ============================================================================
// web-search — Fastify Server Entry Point
//
// POST /api/search — The one and only endpoint.
//
// Request body (JSON):
// {
//   "query": "string (required)",
//   "maxTime": 15000,           // total time limit in ms
//   "maxContentLength": 8000,   // max total content chars returned
//   "perUrlTimeout": 3000,       // timeout per URL in ms
//   "maxPerUrl": 5000            // max chars per single page
// }
// ============================================================================

import Fastify from 'fastify';
import { executePipeline } from './pipeline.js';
import type { WebSearchRequest } from './types.js';

const PORT = parseInt(process.env.PORT || '3003', 10);
const HOST = process.env.HOST || '0.0.0.0';

const app = Fastify({
  logger: true,
  requestTimeout: 60000,
});

// ─── POST /api/search ──────────────────────────────────────────────────────

app.post('/api/search', async (request, reply) => {
  const body = request.body as WebSearchRequest;

  if (!body || !body.query || typeof body.query !== 'string') {
    return reply.status(400).send({
      error: 'Bad Request',
      message: 'Field "query" is required and must be a string.',
    });
  }

  // Sanitize inputs
  const req: WebSearchRequest = {
    query: body.query.trim(),
    maxTime: Math.min(Math.max(body.maxTime ?? 15000, 3000), 60000),
    maxContentLength: Math.min(Math.max(body.maxContentLength ?? 8000, 500), 50000),
    perUrlTimeout: Math.min(Math.max(body.perUrlTimeout ?? 3000, 500), 15000),
    maxPerUrl: Math.min(Math.max(body.maxPerUrl ?? 5000, 500), 30000),
  };

  try {
    const result = await executePipeline(req);
    return reply.send(result);
  } catch (err: any) {
    request.log.error(err);
    return reply.status(500).send({
      error: 'Internal Error',
      message: err.message || 'Unknown error',
    });
  }
});

// ─── GET /healthz ──────────────────────────────────────────────────────────

app.get('/healthz', async () => {
  return { status: 'ok', timestamp: new Date().toISOString() };
});

// ─── Startup ───────────────────────────────────────────────────────────────

async function main() {
  try {
    await app.listen({ port: PORT, host: HOST });
    console.log(`\n  🚀 web-search server running at http://${HOST}:${PORT}`);
    console.log(`  📡 POST /api/search  —  Search + Crawl + Extract\n`);
  } catch (err) {
    app.log.error(err);
    process.exit(1);
  }
}

main();
