import { execFileSync } from 'child_process';
import { brotliDecompressSync, gunzipSync, inflateSync } from 'zlib';
import { Pool, ProxyAgent, request as undiciRequest } from 'undici';
import type { EngineResponse } from '../engines/engine.js';
import type { RequestParams } from '../types.js';

export interface HttpClientOptions {
  connections?: number;
  keepAliveTimeoutMs?: number;
  proxyUrl?: string;
  headersTimeoutMs?: number;
  bodyTimeoutMs?: number;
}

export class HttpClient {
  private readonly pools = new Map<string, Pool>();
  private readonly proxyUrl?: string;
  private readonly proxyAgent?: ProxyAgent;

  constructor(private readonly options: HttpClientOptions = {}) {
    this.proxyUrl = options.proxyUrl ?? detectProxyUrl();
    this.proxyAgent = this.proxyUrl ? new ProxyAgent(this.proxyUrl) : undefined;
  }

  async request(params: RequestParams): Promise<EngineResponse> {
    const cookieHeader = Object.entries(params.cookies || {})
      .map(([key, value]) => `${key}=${value}`)
      .join('; ');

    const headers: Record<string, string> = {
      'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0',
      Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'Accept-Language': 'en-US,en;q=0.5',
      'Accept-Encoding': 'gzip, deflate, br',
      Connection: 'keep-alive',
      ...(cookieHeader ? { Cookie: cookieHeader } : {}),
      ...params.headers,
    };

    const url = params.url ?? "";
    if (!url) throw new Error("HttpClient.request: url is required");
    const response = await this.sendWithRedirects(url, {
      method: params.method || "GET",
      headers,
      body: params.data ? new URLSearchParams(params.data).toString() : undefined,
      headersTimeout: this.options.headersTimeoutMs ?? 12_000,
      bodyTimeout: this.options.bodyTimeoutMs ?? 15_000,
    });

    let decodedText: string | undefined;
    const readText = async () => {
      if (decodedText !== undefined) {
        return decodedText;
      }

      const arrayBuffer = await response.body.arrayBuffer();
      const raw = Buffer.from(arrayBuffer);
      decodedText = decodeBody(raw, response.headers['content-encoding']).toString('utf8');
      return decodedText;
    };

    return {
      status: response.statusCode,
      text: readText,
      json: async () => JSON.parse(await readText()),
      headers: Object.fromEntries(
        Object.entries(response.headers).map(([key, value]) => [
          key,
          Array.isArray(value) ? value.join(', ') : String(value),
        ]),
      ),
      url: response.url,
    };
  }

  /**
   * Convenience method: simple GET request returning response body as string.
   */
  async get(
    url: string,
    options?: { timeout?: number; headers?: Record<string, string> },
  ): Promise<string> {
    const reqParams: RequestParams = {
      query: "",
      url,
      method: "GET",
      headers: options?.headers,
    };
    const resp = await this.request(reqParams);
    return resp.text();
  }

  async close(): Promise<void> {
    await Promise.all([
      ...[...this.pools.values()].map((pool) => pool.close()),
      ...(this.proxyAgent ? [this.proxyAgent.close()] : []),
    ]);
    this.pools.clear();
  }

  private getPool(origin: string): Pool {
    const existing = this.pools.get(origin);
    if (existing) {
      return existing;
    }

    const pool = new Pool(origin, {
      connections: this.options.connections ?? 8,
      keepAliveTimeout: this.options.keepAliveTimeoutMs ?? 10_000,
    });
    this.pools.set(origin, pool);
    return pool;
  }

  private async sendWithRedirects(
    initialUrl: string,
    options: {
      method: string;
      headers: Record<string, string>;
      body?: string;
      headersTimeout: number;
      bodyTimeout: number;
    },
  ): Promise<any> {
    let currentUrl = initialUrl;
    let method = options.method;
    let body = options.body;

    for (let redirectCount = 0; redirectCount <= 3; redirectCount += 1) {
      const url = new URL(currentUrl);
      const response = this.proxyAgent
        ? await (undiciRequest(currentUrl, {
            method,
            headers: options.headers,
            body,
            headersTimeout: options.headersTimeout,
            bodyTimeout: options.bodyTimeout,
            dispatcher: this.proxyAgent,
          } as any) as any)
        : await (this.getPool(url.origin).request({
            method,
            path: `${url.pathname}${url.search}`,
            headers: options.headers,
            body,
            headersTimeout: options.headersTimeout,
            bodyTimeout: options.bodyTimeout,
          } as any) as any);

      const location = response.headers?.location;
      const nextLocation = Array.isArray(location) ? location[0] : location;
      if (!isRedirectStatus(response.statusCode) || !nextLocation || redirectCount === 3) {
        response.url = currentUrl;
        return response;
      }

      if (typeof response.body?.dump === 'function') {
        await response.body.dump();
      }

      currentUrl = new URL(String(nextLocation), currentUrl).toString();
      options.headers.Referer = currentUrl;
      if (response.statusCode === 303 || ((response.statusCode === 301 || response.statusCode === 302) && method === 'POST')) {
        method = 'GET';
        body = undefined;
      }
    }
  }
}

function isRedirectStatus(statusCode: number): boolean {
  return statusCode === 301 || statusCode === 302 || statusCode === 303 || statusCode === 307 || statusCode === 308;
}

function decodeBody(body: Buffer, contentEncoding: unknown): Buffer {
  const encoding = String(Array.isArray(contentEncoding) ? contentEncoding[0] : contentEncoding ?? '')
    .split(',')
    .map((part) => part.trim().toLowerCase())
    .filter(Boolean)[0];

  try {
    if (encoding === 'gzip' || encoding === 'x-gzip') {
      return gunzipSync(body);
    }
    if (encoding === 'br') {
      return brotliDecompressSync(body);
    }
    if (encoding === 'deflate') {
      return inflateSync(body);
    }
  } catch {
    return body;
  }

  return body;
}

function detectProxyUrl(): string | undefined {
  const envProxy =
    process.env.HTTPS_PROXY ||
    process.env.https_proxy ||
    process.env.HTTP_PROXY ||
    process.env.http_proxy ||
    process.env.ALL_PROXY ||
    process.env.all_proxy;

  if (envProxy) {
    return normalizeProxyUrl(envProxy);
  }

  if (process.platform !== 'win32') {
    return undefined;
  }

  try {
    const output = execFileSync(
      'reg',
      [
        'query',
        'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings',
        '/v',
        'ProxyEnable',
      ],
      { encoding: 'utf8', windowsHide: true },
    );
    if (!/ProxyEnable\s+REG_DWORD\s+0x1/i.test(output)) {
      return undefined;
    }

    const serverOutput = execFileSync(
      'reg',
      [
        'query',
        'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings',
        '/v',
        'ProxyServer',
      ],
      { encoding: 'utf8', windowsHide: true },
    );
    const match = serverOutput.match(/ProxyServer\s+REG_SZ\s+(.+)/i);
    return match ? normalizeProxyUrl(parseProxyServer(match[1].trim())) : undefined;
  } catch {
    return undefined;
  }
}

function parseProxyServer(proxyServer: string): string {
  if (!proxyServer.includes(';')) {
    return proxyServer;
  }

  const entries = proxyServer.split(';').map((entry) => entry.trim());
  const httpsEntry = entries.find((entry) => entry.toLowerCase().startsWith('https='));
  const httpEntry = entries.find((entry) => entry.toLowerCase().startsWith('http='));
  return (httpsEntry ?? httpEntry ?? entries[0]).replace(/^[a-z]+=/i, '');
}

function normalizeProxyUrl(proxy: string): string {
  return /^[a-z][a-z0-9+.-]*:\/\//i.test(proxy) ? proxy : `http://${proxy}`;
}

/** 默认 HttpClient 实例，供简单 GET 请求使用 */
export const httpClient = new HttpClient();
