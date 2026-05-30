import { executePipeline } from './dist/pipeline.js';

function readPayload() {
  const raw = process.argv[2] || '{}';
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw new Error(`Invalid JSON payload: ${error.message}`);
  }
}

function clamp(value, fallback, min, max) {
  const n = Number(value ?? fallback);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(Math.max(Math.trunc(n), min), max);
}

async function main() {
  const payload = readPayload();
  const req = {
    query: String(payload.query || '').trim(),
    maxTime: clamp(payload.maxTime, 15000, 3000, 45000),
    maxContentLength: clamp(payload.maxContentLength, 8000, 500, 50000),
    perUrlTimeout: clamp(payload.perUrlTimeout, 3000, 500, 15000),
    maxPerUrl: clamp(payload.maxPerUrl, 5000, 500, 30000),
  };

  if (!req.query) {
    throw new Error('query is required');
  }

  const result = await executePipeline(req);
  process.stdout.write(JSON.stringify(result));
}

main().catch((error) => {
  process.stderr.write(error?.stack || String(error));
  process.exit(1);
});
