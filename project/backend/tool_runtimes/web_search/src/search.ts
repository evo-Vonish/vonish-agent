// ============================================================================
// web-search — Multi-Engine Search Orchestrator & URL Merger
//
// Ported from Mini-SearXNG orchestrator + merger.
// Searches all engines in parallel, merges & deduplicates by URL,
// then scores results using SearXNG's calculate_score algorithm.
// ============================================================================

import type { RawSearchResult, MergedUrl } from './types.js';
import { ALL_ENGINES, type EngineAdapter } from './engines.js';

// ─── URL Normalization ─────────────────────────────────────────────────────

const TRACKING_PARAMS = new Set([
  'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
  'utm_id', 'fbclid', 'gclid', 'gbraid', 'wbraid', 'msclkid', 'dclid',
  'twclid', 'mc_cid', 'mc_eid', '_ga', '_gid',
]);

function normalizeUrl(raw: string): string {
  try {
    const u = new URL(raw.trim());
    u.hash = '';
    for (const p of TRACKING_PARAMS) {
      u.searchParams.delete(p);
    }
    return u.toString();
  } catch {
    return raw;
  }
}

// ─── Multi-Engine Parallel Search ──────────────────────────────────────────

interface SearchResult {
  results: MergedUrl[];
  elapsedMs: number;
}

export async function multiSearch(
  query: string,
  engines?: EngineAdapter[],
): Promise<SearchResult> {
  const t0 = performance.now();
  const activeEngines = engines ?? ALL_ENGINES;

  // Launch all engines in parallel with individual timeouts
  const tasks = activeEngines.map((engine) =>
    Promise.race([
      engine.search(query),
      new Promise<RawSearchResult[]>((_, reject) =>
        setTimeout(
          () => reject(new Error(`${engine.name}: timeout`)),
          engine.timeoutMs,
        ),
      ),
    ]).catch(() => [] as RawSearchResult[]),
  );

  const engineResults = await Promise.all(tasks);

  // Merge & deduplicate by normalized URL
  const urlMap = new Map<string, MergedUrl>();
  const engineWeights = new Map(
    activeEngines.map((e) => [e.name, e.weight]),
  );

  for (let ei = 0; ei < engineResults.length; ei++) {
    const engine = activeEngines[ei];
    const results = engineResults[ei];
    for (const raw of results) {
      const key = normalizeUrl(raw.url);
      const existing = urlMap.get(key);

      if (existing) {
        // Merge: track engines and positions
        if (!existing.engines.includes(engine.name)) {
          existing.engines.push(engine.name);
        }
        existing.positions.push(raw.position);
        // Prefer longer title/snippet
        if (raw.title.length > existing.title.length) {
          existing.title = raw.title;
        }
        if ((raw.snippet || '').length > existing.snippet.length) {
          existing.snippet = raw.snippet || existing.snippet;
        }
      } else {
        urlMap.set(key, {
          title: raw.title,
          url: raw.url,
          snippet: raw.snippet || '',
          engines: [engine.name],
          positions: [raw.position],
          score: 0,
        });
      }
    }
  }

  // Calculate SearXNG-style scores
  const merged: MergedUrl[] = [];
  for (const item of urlMap.values()) {
    let weight = 1.0;
    for (const eng of item.engines) {
      weight *= engineWeights.get(eng) ?? 1.0;
    }
    weight *= item.positions.length;

    let score = 0;
    for (const pos of item.positions) {
      score += weight / pos;
    }
    item.score = score;
    merged.push(item);
  }

  // Sort by score descending
  merged.sort((a, b) => b.score - a.score);

  return {
    results: merged,
    elapsedMs: Math.round(performance.now() - t0),
  };
}
