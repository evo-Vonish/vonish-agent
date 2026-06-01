/**
 * Ultra Fetcher — enterprise-grade HTTP fetch with layered timeouts,
 * TCP fast-fail probe, stream truncation, and undici Agent.
 */

import { request } from 'undici';
import { Socket } from 'net';
import { brotliDecompressSync, gunzipSync, inflateSync } from 'zlib';
import type { FetchResult } from '../types.js';

const DEFAULT_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0';

export interface UltraFetchOptions {
  url: string;
  timeoutMs?: number;
  connectTimeoutMs?: number;
  userAgent?: string;
  streamLimitBytes?: number;
  redirectCount?: number;
}

// ─── TCP Fast-Fail Probe ────────────────────────────────────────

/**
 * Quick TCP connection probe — determines if host is reachable.
 * Returns within 500ms (unreachable) or on connect (reachable).
 */
export async function probeConnection(
  hostname: string,
  port: number = 443,
  timeoutMs: number = 500,
): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new Socket();
    let resolved = false;

    const cleanup = () => {
      if (!resolved) {
        resolved = true;
        socket.destroy();
      }
    };

    socket.setTimeout(timeoutMs);
    socket.once('connect', () => {
      cleanup();
      resolve(true);
    });
    socket.once('timeout', () => {
      cleanup();
      resolve(false);
    });
    socket.once('error', () => {
      cleanup();
      resolve(false);
    });

    socket.connect(port, hostname);
  });
}

// ─── Ultra Fetch ────────────────────────────────────────────────

/**
 * Fetch a single page with enterprise-grade performance:
 * - TCP probe first (500ms fast-fail)
 * - undici request with true socket-level timeouts
 * - Stream truncation (stop reading after limit)
 * - No retries (retries waste time budget)
 */
export async function ultraFetch(opts: UltraFetchOptions): Promise<FetchResult> {
  const start = Date.now();
  const url = opts.url;
  const timeoutMs = opts.timeoutMs ?? 2500;
  const connectTimeoutMs = opts.connectTimeoutMs ?? 800;
  const streamLimit = opts.streamLimitBytes ?? 200 * 1024;
  const userAgent = opts.userAgent || DEFAULT_UA;

  // Step 1: TCP fast-fail probe
  try {
    const { hostname, protocol } = new URL(url);
    const port = protocol === 'https:' ? 443 : 80;
    const reachable = await probeConnection(hostname, port, connectTimeoutMs);
    if (!reachable) {
      return {
        html: '',
        finalUrl: url,
        statusCode: 0,
        contentType: '',
        durationMs: Date.now() - start,
      };
    }
  } catch {
    // Probe failed — try direct fetch anyway
  }

  // Step 2: undici request with true socket-level timeout
  try {
    const { statusCode, headers, body } = await request(url, {
      method: 'GET',
      headers: {
        'User-Agent': userAgent,
        Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'identity',
        Connection: 'keep-alive',
      },
      bodyTimeout: timeoutMs,
      headersTimeout: Math.min(timeoutMs, 2000),
    });

    // Non-2xx status
    if (statusCode < 200 || statusCode >= 300) {
      body.destroy();
      return {
        html: '',
        finalUrl: url,
        statusCode,
        contentType: (headers['content-type'] as string) || '',
        durationMs: Date.now() - start,
      };
    }

    // Step 3: Stream read with truncation
    const chunks: Buffer[] = [];
    let totalLen = 0;

    try {
      for await (const chunk of body) {
        totalLen += chunk.length;
        chunks.push(chunk);
        if (totalLen >= streamLimit) {
          body.destroy();
          break;
        }
      }
    } catch {
      // Stream error — use what we have
    }

    const bodyBuffer = Buffer.concat(chunks);
    const encoding = String(headers['content-encoding'] || '').toLowerCase();
    const decoded =
      encoding.includes('br')
        ? brotliDecompressSync(bodyBuffer)
        : encoding.includes('gzip')
          ? gunzipSync(bodyBuffer)
          : encoding.includes('deflate')
            ? inflateSync(bodyBuffer)
            : bodyBuffer;
    const html = decoded.toString('utf-8');

    return {
      html,
      finalUrl: url,
      statusCode,
      contentType: (headers['content-type'] as string) || '',
      durationMs: Date.now() - start,
    };
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);

    // Classify error
    if (msg.includes('timeout') || msg.includes('Timeout')) {
      return {
        html: '',
        finalUrl: url,
        statusCode: 0,
        contentType: '',
        durationMs: Date.now() - start,
      };
    }

    return {
      html: '',
      finalUrl: url,
      statusCode: 0,
      contentType: '',
      durationMs: Date.now() - start,
    };
  }
}
