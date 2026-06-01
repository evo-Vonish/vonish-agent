import { Socket } from 'net';
import { Agent, request } from 'undici';

/**
 * Configuration options for a single page fetch operation.
 */
export interface FetchOptions {
  /** Target URL to fetch. */
  url: string;
  /** Maximum time to wait for the response, in milliseconds. */
  timeoutMs: number;
  /** Custom User-Agent string (uses a Firefox default when omitted). */
  userAgent?: string;
  /** Number of retries on failure (default: 0). */
  retryCount?: number;
  /** Optional external signal used to cancel the request early. */
  signal?: AbortSignal;
  /** TCP connect probe timeout. */
  connectTimeoutMs?: number;
  /** Response header timeout. */
  headersTimeoutMs?: number;
  /** Maximum number of response bytes to read. */
  streamLimitBytes?: number;
}

/** Default Firefox User-Agent string used when none is provided. */
const DEFAULT_USER_AGENT =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0';

/** Additional delay added per retry attempt (exponential backoff base, ms). */
const RETRY_BACKOFF_MS = 500;

/** Maximum body size in bytes (~10 MB) to prevent memory exhaustion. */
const MAX_BODY_SIZE = 10 * 1024 * 1024;

const DEFAULT_CONNECT_TIMEOUT_MS = 800;
const DEFAULT_STREAM_LIMIT_BYTES = 500 * 1024;

const globalAgent = new Agent({
  connect: {
    timeout: DEFAULT_CONNECT_TIMEOUT_MS,
    rejectUnauthorized: false,
  },
  keepAliveTimeout: 30_000,
  keepAliveMaxTimeout: 60_000,
  connections: 50,
  pipelining: 1,
} as any);

/**
 * Result of a successful page fetch.
 */
export interface FetchResult {
  /** Raw HTML response body as a string. */
  html: string;
  /** Final URL after following redirects (may differ from the request URL). */
  finalUrl: string;
  /** Total elapsed time from start to finish, in milliseconds. */
  durationMs: number;
}

/**
 * Fetch a single page with timeout, redirect following, and retry support.
 *
 * @param options - Fetch configuration including URL, timeout, and retry policy.
 * @returns A {@link FetchResult} containing the HTML, final URL, and timing info.
 * @throws When the request times out (`'TIMEOUT'`), exceeds max redirects,
 *         the response body is too large, or all retry attempts are exhausted.
 *
 * @example
 * ```ts
 * const { html, finalUrl, durationMs } = await fetchPage({
 *   url: 'https://example.com/article',
 *   timeoutMs: 5000,
 *   retryCount: 1,
 * });
 * ```
 */
export async function fetchPage(options: FetchOptions): Promise<FetchResult> {
  const {
    url,
    timeoutMs,
    userAgent,
    retryCount = 0,
    signal,
    connectTimeoutMs = DEFAULT_CONNECT_TIMEOUT_MS,
    headersTimeoutMs = Math.min(timeoutMs, 2000),
    streamLimitBytes = DEFAULT_STREAM_LIMIT_BYTES,
  } = options;

  // Validate URL
  let validatedUrl: string;
  try {
    validatedUrl = new URL(url).href;
  } catch {
    throw new Error(`Invalid URL: ${url}`);
  }

  // Keep track of timing across retries
  const startTime = Date.now();
  let lastError: Error | undefined;

  // Total attempts = 1 initial + retryCount retries
  const maxAttempts = Math.max(1, retryCount + 1);

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const result = await fetchSingleAttempt({
        url: validatedUrl,
        timeoutMs,
        userAgent,
        signal,
        connectTimeoutMs,
        headersTimeoutMs,
        streamLimitBytes,
      });
      const durationMs = Date.now() - startTime;
      return { ...result, durationMs };
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));

      // Don't retry on timeout errors
      if (lastError.message === 'TIMEOUT' || lastError.message === 'CONNECT_TIMEOUT') {
        throw lastError;
      }

      // If we have retries left, wait with exponential backoff then retry
      if (attempt < maxAttempts - 1) {
        const delay = RETRY_BACKOFF_MS * (attempt + 1);
        await sleep(delay);
      }
    }
  }

  // All attempts exhausted — throw the last error
  throw lastError ?? new Error(`Failed to fetch ${validatedUrl}`);
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Perform a single fetch attempt with timeout and redirect following.
 *
 * @internal
 */
async function fetchSingleAttempt(options: {
  url: string;
  timeoutMs: number;
  userAgent?: string;
  signal?: AbortSignal;
  connectTimeoutMs: number;
  headersTimeoutMs: number;
  streamLimitBytes: number;
}): Promise<Pick<FetchResult, 'html' | 'finalUrl'>> {
  const { url, timeoutMs, userAgent, signal, connectTimeoutMs, headersTimeoutMs, streamLimitBytes } = options;

  if (signal?.aborted) {
    throw new Error('TIMEOUT');
  }

  const reachable = await fastConnectProbe(url, connectTimeoutMs, signal);
  if (!reachable) {
    throw new Error('CONNECT_TIMEOUT');
  }

  try {
    const response = await request(url, {
      dispatcher: globalAgent,
      method: 'GET',
      headers: {
        'User-Agent': userAgent || DEFAULT_USER_AGENT,
        Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        Connection: 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
      },
      bodyTimeout: timeoutMs,
      headersTimeout: headersTimeoutMs,
      signal,
      maxRedirections: 3,
    } as any);

    if (response.statusCode < 200 || response.statusCode >= 300) {
      response.body.destroy();
      throw new Error(`HTTP error ${response.statusCode} for ${url}`);
    }

    const contentLength = response.headers['content-length'];
    const lengthHeader = Array.isArray(contentLength) ? contentLength[0] : contentLength;
    if (lengthHeader && parseInt(String(lengthHeader), 10) > MAX_BODY_SIZE) {
      response.body.destroy();
      throw new Error(
        `Response body too large: ${lengthHeader} bytes exceeds limit of ${MAX_BODY_SIZE} bytes`,
      );
    }

    const chunks: Buffer[] = [];
    let totalLength = 0;
    for await (const chunk of response.body as any as AsyncIterable<Buffer>) {
      const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      chunks.push(buffer);
      totalLength += buffer.length;

      if (totalLength > MAX_BODY_SIZE) {
        response.body.destroy();
        throw new Error(
          `Response body too large: ${totalLength} bytes exceeds limit of ${MAX_BODY_SIZE} bytes`,
        );
      }

      if (totalLength >= streamLimitBytes) {
        response.body.destroy();
        break;
      }
    }

    return { html: Buffer.concat(chunks).toString('utf-8'), finalUrl: url };
  } catch (err: unknown) {
    if (err instanceof Error) {
      if (
        err.name === 'AbortError' ||
        err.name === 'TimeoutError' ||
        /aborted|body timeout|headers timeout/i.test(err.message)
      ) {
        throw new Error('TIMEOUT');
      }
    }
    throw err;
  }
}

/**
 * Pause execution for a given number of milliseconds.
 *
 * @internal
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function fastConnectProbe(url: string, timeoutMs: number, signal?: AbortSignal): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    let parsed: URL;
    try {
      parsed = new URL(url);
    } catch {
      resolve(false);
      return;
    }

    const port = parsed.port ? Number(parsed.port) : parsed.protocol === 'http:' ? 80 : 443;
    const socket = new Socket();
    const finish = (value: boolean): void => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener('abort', onAbort);
      socket.destroy();
      resolve(value);
    };
    const onAbort = (): void => finish(false);

    signal?.addEventListener('abort', onAbort, { once: true });
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => finish(true));
    socket.once('timeout', () => finish(false));
    socket.once('error', () => finish(false));
    socket.connect(port, parsed.hostname);
  });
}
