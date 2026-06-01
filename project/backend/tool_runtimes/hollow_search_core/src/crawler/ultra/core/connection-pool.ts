/**
 * Enterprise connection pool — undici Agent with HTTP/2, DNS cache, TLS session cache.
 *
 * Key design: one global Agent shared across all requests for connection reuse.
 * HTTP/2 multiplexing allows 100+ concurrent streams over a single TCP connection.
 */

import { Agent, Pool } from 'undici';

// ─── Default agent options (tuned for high-concurrency crawling) ─

const DEFAULT_AGENT_OPTIONS = {
  connect: {
    timeout: 800,
    rejectUnauthorized: false,
    maxCachedSessions: 100,
  },
  bodyTimeout: 2500,
  headersTimeout: 1500,
  keepAliveTimeout: 30000,
  keepAliveMaxTimeout: 30,
  connections: 100,
  pipelining: 1,
  allowH2: true,
} as const;

// ─── Global shared agent (singleton) ────────────────────────────

let globalAgent: Agent | null = null;

/** Get (or create) the global undici Agent */
export function getGlobalAgent(): Agent {
  if (!globalAgent) {
    globalAgent = new Agent(DEFAULT_AGENT_OPTIONS);
  }
  return globalAgent;
}

/** Create a custom agent with specific options */
export function createAgent(opts?: {
  connectTimeout?: number;
  bodyTimeout?: number;
  headersTimeout?: number;
  maxSockets?: number;
  allowH2?: boolean;
}): Agent {
  return new Agent({
    connect: {
      timeout: opts?.connectTimeout ?? 800,
      rejectUnauthorized: false,
      maxCachedSessions: 100,
    },
    bodyTimeout: opts?.bodyTimeout ?? 2500,
    headersTimeout: opts?.headersTimeout ?? 1500,
    keepAliveTimeout: 30000,
    keepAliveMaxTimeout: 30,
    connections: opts?.maxSockets ?? 100,
    pipelining: 1,
    allowH2: opts?.allowH2 ?? true,
  });
}

/** Domain-specific connection pools for targeted optimization */
const domainPools = new Map<string, Pool>();

/** Get or create a domain-specific pool */
export function getDomainPool(domain: string): Pool {
  if (!domainPools.has(domain)) {
    domainPools.set(
      domain,
      new Pool(`https://${domain}`, {
        connections: 10,
        connect: { timeout: 800, rejectUnauthorized: false },
        bodyTimeout: 2500,
        headersTimeout: 1500,
        keepAliveTimeout: 30000,
        pipelining: 1,
      }),
    );
  }
  return domainPools.get(domain)!;
}

/** Warm up connections to a list of domains (pre-connect) */
export async function warmConnections(domains: string[]): Promise<void> {
  await Promise.all(
    domains.map(async (domain) => {
      try {
        const pool = getDomainPool(domain);
        await pool.request({
          method: 'HEAD',
          path: '/',
          headers: { 'User-Agent': 'Mozilla/5.0 (compatible; MiniSearXNG/1.0)' },
        });
      } catch {
        // Warm-up failure is non-fatal
      }
    }),
  );
}

/** Extract domain from URL */
export function extractDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return 'unknown';
  }
}

/** Group URLs by domain for connection reuse optimization */
export function groupByDomain(urls: string[]): Map<string, string[]> {
  const groups = new Map<string, string[]>();
  for (const url of urls) {
    const domain = extractDomain(url);
    if (!groups.has(domain)) groups.set(domain, []);
    groups.get(domain)!.push(url);
  }
  return groups;
}

/** Close all domain pools and global agent */
export async function closeAllPools(): Promise<void> {
  const closePromises: Promise<unknown>[] = [];

  for (const [, pool] of domainPools) {
    closePromises.push(pool.close());
  }
  domainPools.clear();

  if (globalAgent) {
    closePromises.push(globalAgent.close());
    globalAgent = null;
  }

  await Promise.all(closePromises);
}
