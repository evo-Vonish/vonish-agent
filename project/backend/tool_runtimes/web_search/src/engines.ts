// ============================================================================
// web-search — Search Engine Adapters
//
// Bing (cn.bing.com) + Sogou (sogou.com) + 360 (so.com)
// No API keys required — all three work from mainland China.
// ============================================================================

import * as cheerio from 'cheerio';
import { request as undiciRequest, ProxyAgent } from 'undici';
import { brotliDecompressSync, gunzipSync, inflateSync } from 'zlib';
import type { RawSearchResult } from './types.js';

// ─── Engine Interface ─────────────────────────────────────────────────────

export interface EngineAdapter {
  readonly name: string;
  readonly weight: number;
  readonly timeoutMs: number;
  search(query: string): Promise<RawSearchResult[]>;
}

// ─── Proxy Detection ──────────────────────────────────────────────────────

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

// ─── Decompression ─────────────────────────────────────────────────────────

function decodeBody(body: Buffer, encoding: string): Buffer {
  try {
    if (encoding === 'gzip' || encoding === 'x-gzip') return gunzipSync(body);
    if (encoding === 'br') return brotliDecompressSync(body);
    if (encoding === 'deflate') return inflateSync(body);
  } catch {}
  return body;
}

// ─── HTTP Helper ───────────────────────────────────────────────────────────

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
const UA_FIREFOX = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0';

async function fetchWithUndici(
  url: string,
  opts: {
    method?: 'GET' | 'POST';
    headers?: Record<string, string>;
    body?: string;
    timeoutMs?: number;
  } = {},
): Promise<{ status: number; text: string }> {
  const dispatcher = PROXY_URL ? new ProxyAgent(PROXY_URL) : undefined;
  let currentUrl = url;
  let method = opts.method || 'GET';
  let body = opts.body;
  const timeout = opts.timeoutMs || 8000;

  for (let redirects = 0; redirects <= 5; redirects++) {
    try {
      const resp = await undiciRequest(currentUrl, {
        method,
        headers: { ...opts.headers },
        body: method === 'POST' ? body : undefined,
        dispatcher,
        bodyTimeout: timeout,
        headersTimeout: 5000,
      });

      if ([301, 302, 303, 307, 308].includes(resp.statusCode)) {
        const location = (resp.headers as any)['location'];
        if (location) {
          try { resp.body?.resume(); resp.body?.on('error', () => {}); } catch {}
          currentUrl = new URL(String(location), currentUrl).toString();
          if (resp.statusCode === 303 || (resp.statusCode === 302 && method === 'POST')) {
            method = 'GET'; body = undefined;
          }
          continue;
        }
      }

      const chunks: Buffer[] = [];
      try { for await (const chunk of resp.body!) chunks.push(chunk); } catch { /* stream end */ }
      const raw = Buffer.concat(chunks);
      const ce = String((resp.headers as any)['content-encoding'] || '').toLowerCase().trim();
      const decoded = decodeBody(raw, ce);
      return { status: resp.statusCode, text: decoded.toString('utf-8') };
    } catch (err: any) {
      throw new Error(err.message || 'fetch failed');
    }
  }
  throw new Error('Too many redirects');
}

// ═══════════════════════════════════════════════════════════════════════════
//  Bing Engine (cn.bing.com)
// ═══════════════════════════════════════════════════════════════════════════

class BingEngine implements EngineAdapter {
  readonly name = 'bing';
  readonly weight = 1.0;
  readonly timeoutMs = 8000;

  async search(query: string): Promise<RawSearchResult[]> {
    try {
      const url = `https://cn.bing.com/search?q=${encodeURIComponent(query)}`;
      const { text: html } = await fetchWithUndici(url, {
        headers: {
          'User-Agent': UA_FIREFOX,
          'Accept': 'text/html,application/xhtml+xml',
          'Accept-Language': 'zh-CN,zh;q=0.9',
        },
        timeoutMs: this.timeoutMs,
      });
      if (!html) return [];

      const $ = cheerio.load(html);
      const results: RawSearchResult[] = [];

      $('li.b_algo').each((i: number, el: any) => {
        const h2a = $(el).find('h2 a').first();
        const title = h2a.text().trim();
        const url = h2a.attr('href') || '';
        const snippet = $(el).find('.b_caption p, .b_lineclamp2').first().text().trim();
        if (title && url) {
          results.push({ title, url, snippet: snippet || undefined, engine: 'bing', position: i + 1 });
        }
      });
      return results.slice(0, 15);
    } catch {
      return [];
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  Sogou Engine (sogou.com)
// ═══════════════════════════════════════════════════════════════════════════

class SogouEngine implements EngineAdapter {
  readonly name = 'sogou';
  readonly weight = 1.0;
  readonly timeoutMs = 8000;

  async search(query: string): Promise<RawSearchResult[]> {
    try {
      const url = `https://www.sogou.com/web?query=${encodeURIComponent(query)}`;
      const { text: html } = await fetchWithUndici(url, {
        headers: {
          'User-Agent': UA,
          'Accept': 'text/html',
          'Accept-Language': 'zh-CN,zh;q=0.9',
        },
        timeoutMs: this.timeoutMs,
      });
      if (!html) return [];

      const $ = cheerio.load(html);
      const results: RawSearchResult[] = [];

      // Sogou result containers
      $('.results .vrwrap, .results .rb').each((i: number, el: any) => {
        const h3a = $(el).find('h3 a').first();
        const title = h3a.text().trim() || $(el).find('.vr_title a').text().trim();
        const url = h3a.attr('href') || '';
        const snippet = $(el).find('.star-wiki, .str-text, .space-txt').text().trim()
          || $(el).find('.str_info, .str_info_div').text().trim()
          || $(el).find('p').first().text().trim();

        if (title && url && !url.startsWith('javascript:')) {
          results.push({ title, url, snippet: snippet.slice(0, 300) || undefined, engine: 'sogou', position: i + 1 });
        }
      });

      // Fallback: direct h3 links
      if (results.length === 0) {
        $('.results h3 a').each((i: number, el: any) => {
          const title = $(el).text().trim();
          const url = $(el).attr('href') || '';
          if (title && url) {
            results.push({ title, url, engine: 'sogou', position: i + 1 });
          }
        });
      }

      return results.slice(0, 15);
    } catch {
      return [];
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  360 Search Engine (so.com)
// ═══════════════════════════════════════════════════════════════════════════

class So360Engine implements EngineAdapter {
  readonly name = '360';
  readonly weight = 0.9;
  readonly timeoutMs = 8000;

  async search(query: string): Promise<RawSearchResult[]> {
    try {
      const url = `https://www.so.com/s?q=${encodeURIComponent(query)}`;
      const { text: html } = await fetchWithUndici(url, {
        headers: {
          'User-Agent': UA,
          'Accept': 'text/html',
          'Accept-Language': 'zh-CN,zh;q=0.9',
        },
        timeoutMs: this.timeoutMs,
      });
      if (!html) return [];

      const $ = cheerio.load(html);
      const results: RawSearchResult[] = [];

      $('.res-list, .result').each((i: number, el: any) => {
        const h3a = $(el).find('h3 a').first();
        const title = h3a.text().trim();
        const url = h3a.attr('href') || '';
        const snippet = $(el).find('.res-desc, .res-rich, .result-about').text().trim()
          || $(el).find('p').first().text().trim();

        if (title && url) {
          results.push({ title, url, snippet: snippet.slice(0, 300) || undefined, engine: '360', position: i + 1 });
        }
      });

      // Fallback
      if (results.length === 0) {
        $('h3 a, .title a').each((i: number, el: any) => {
          const title = $(el).text().trim();
          const url = $(el).attr('href') || '';
          if (title && url) {
            results.push({ title, url, engine: '360', position: i + 1 });
          }
        });
      }

      return results.slice(0, 15);
    } catch {
      return [];
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  Engine Registry (only engines working on mainland China network)
// ═══════════════════════════════════════════════════════════════════════════

const ALL_ENGINES: EngineAdapter[] = [
  new BingEngine(),
  new SogouEngine(),
  new So360Engine(),
];

export { ALL_ENGINES, BingEngine, SogouEngine, So360Engine };
