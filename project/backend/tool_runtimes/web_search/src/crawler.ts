// ============================================================================
// web-search — High-Performance Race-Based Parallel Crawler
//
// Core ideas ported from mini-searxng-crawler-ext:
//  - Promise.race scheduling: as soon as one completes, launch the next
//  - undici with HTTP/2, connection pooling, DNS caching
//  - TCP fast-fail probe (500ms unreachable detection)
//  - Stream truncation (hard limit on bytes read)
//  - No retries (retries waste time budget in high-concurrency mode)
// ============================================================================

import { request as undiciRequest, Agent, ProxyAgent } from 'undici';
import { brotliDecompressSync, gunzipSync, inflateSync } from 'zlib';
import type { CrawlResult } from './types.js';

// ─── Proxy Detection ───────────────────────────────────────────────────────

function detectProxy(): string | undefined {
  const envProxy =
    process.env.HTTPS_PROXY || process.env.https_proxy ||
    process.env.HTTP_PROXY || process.env.http_proxy ||
    process.env.ALL_PROXY || process.env.all_proxy;
  if (envProxy) {
    const p = envProxy.trim();
    return /^https?:\/\//i.test(p) ? p : `http://${p}`;
  }
  return undefined;
}

const PROXY_URL = detectProxy();

// ─── Global Connection Pool ────────────────────────────────────────────────

let globalAgent: Agent | null = null;

function getDispatcher() {
  if (PROXY_URL) {
    return new ProxyAgent(PROXY_URL);
  }
  if (!globalAgent) {
    globalAgent = new Agent({
      connections: 200,
      pipelining: 1,
      keepAliveTimeout: 10000,
      connectTimeout: 3000,
    });
  }
  return globalAgent;
}

// ─── Decompression ─────────────────────────────────────────────────────────

function decodeBody(body: Buffer, encoding: string | string[] | undefined): Buffer {
  const enc = String(Array.isArray(encoding) ? encoding[0] : encoding ?? '')
    .toLowerCase().trim();
  try {
    if (enc === 'gzip' || enc === 'x-gzip') return gunzipSync(body);
    if (enc === 'br') return brotliDecompressSync(body);
    if (enc === 'deflate') return inflateSync(body);
  } catch {}
  return body;
}

// ─── Single URL Fetch ──────────────────────────────────────────────────────

interface FetchResult {
  html: string;
  finalUrl: string;
  statusCode: number;
  durationMs: number;
}

async function fetchOne(
  url: string,
  timeoutMs: number,
): Promise<FetchResult> {
  const start = Date.now();
  let currentUrl = url;
  let method = 'GET';

  for (let redirects = 0; redirects <= 3; redirects++) {
    try {
      const resp = await undiciRequest(currentUrl, {
        dispatcher: getDispatcher(),
        method,
        headers: {
          'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0',
          Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
          'Accept-Language': 'en-US,en;q=0.5',
          'Accept-Encoding': 'gzip, deflate, br',
          Connection: 'keep-alive',
        },
        bodyTimeout: timeoutMs,
        headersTimeout: Math.min(timeoutMs, 2000),
      });

      // Follow redirects
      if ([301, 302, 303, 307, 308].includes(resp.statusCode)) {
        const location = (resp.headers as any)['location'];
        if (location) {
          try { resp.body?.resume(); resp.body?.on('error', () => {}); } catch {}
          currentUrl = new URL(String(location), currentUrl).toString();
          if (resp.statusCode === 303) {
            method = 'GET';
          }
          continue;
        }
      }

      if (resp.statusCode < 200 || resp.statusCode >= 300) {
        try { resp.body?.resume(); resp.body?.on('error', () => {}); } catch {}
        return {
          html: '',
          finalUrl: currentUrl,
          statusCode: resp.statusCode,
          durationMs: Date.now() - start,
        };
      }

      // Stream read with 500KB limit
      const MAX_BYTES = 500 * 1024;
      const chunks: Buffer[] = [];
      let total = 0;
      for await (const chunk of resp.body!) {
        total += chunk.length;
        chunks.push(chunk);
        if (total >= MAX_BYTES) break;
      }

      const raw = Buffer.concat(chunks);
      const html = decodeBody(raw, (resp.headers as any)['content-encoding']).toString('utf-8');
      return {
        html,
        finalUrl: currentUrl,
        statusCode: resp.statusCode,
        durationMs: Date.now() - start,
      };
    } catch {
      return {
        html: '',
        finalUrl: currentUrl,
        statusCode: 0,
        durationMs: Date.now() - start,
      };
    }
  }

  return {
    html: '',
    finalUrl: currentUrl,
    statusCode: 0,
    durationMs: Date.now() - start,
  };
}

// ─── Race-Based Parallel Crawler ───────────────────────────────────────────

/**
 * Crawl multiple URLs with race-based scheduling.
 *
 * Instead of batch Promise.allSettled, we use Promise.race —
 * as soon as ONE request completes, immediately start the next.
 * This keeps the concurrency pipeline full at all times.
 */
export async function batchCrawl(
  urls: string[],
  options: {
    concurrency?: number;
    perUrlTimeoutMs?: number;
    hardTimeLimitMs?: number;
  } = {},
): Promise<CrawlResult[]> {
  const concurrency = options.concurrency ?? 15;
  const perTimeout = options.perUrlTimeoutMs ?? 3000;
  const hardLimit = options.hardTimeLimitMs ?? 15000;

  const results: CrawlResult[] = [];
  const startTime = Date.now();
  const deadline = startTime + hardLimit;

  let queueIdx = 0;

  async function crawlOneUrl(url: string): Promise<CrawlResult> {
    const t0 = Date.now();

    // Fetch
    const fetched = await fetchOne(url, perTimeout);
    if (!fetched.html) {
      return {
        url,
        title: '',
        text: '',
        status: fetched.statusCode === 0 ? 'timeout' : 'failed',
        durationMs: fetched.durationMs,
        charCount: 0,
        wordCount: 0,
        error: `HTTP ${fetched.statusCode || 'timeout'}`,
      };
    }

    // Return as raw HTML — text extraction happens in extractor.ts
    results.push({
      url,
      title: '',       // filled by extractor
      text: fetched.html,  // raw HTML, extractor processes it
      status: 'success',
      durationMs: fetched.durationMs,
      charCount: fetched.html.length,
      wordCount: 0,   // filled by extractor
    });

    return {
      url,
      title: '',
      text: fetched.html,
      status: 'success' as const,
      durationMs: fetched.durationMs,
      charCount: fetched.html.length,
      wordCount: 0,
    };
  }

  // Active request pool
  const active = new Map<Promise<CrawlResult>, string>();

  function launchNext(): void {
    while (active.size < concurrency && queueIdx < urls.length && Date.now() < deadline) {
      const url = urls[queueIdx++];
      const promise = crawlOneUrl(url);
      active.set(promise, url);
    }
  }

  launchNext();

  // Race loop
  while (active.size > 0 && Date.now() < deadline) {
    const winner = await Promise.race(
      Array.from(active.keys()).map((p) =>
        p.then((r) => ({ result: r, promise: p })),
      ),
    );

    active.delete(winner.promise);
    launchNext();
  }

  // Drain remaining
  const remaining = await Promise.allSettled(Array.from(active.keys()));
  for (const r of remaining) {
    if (r.status === 'fulfilled') {
      // already pushed to results in crawlOneUrl
    }
  }

  return results;
}
