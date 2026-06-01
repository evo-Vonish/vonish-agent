/**
 * Result merger + deduplicator – TypeScript port of SearXNG results.py.
 *
 * Responsibilities:
 *   1. Collect RawResult items from every successful EngineResponse.
 *   2. Normalise URLs and deduplicate by normalised URL (Map key).
 *   3. Merge fields for duplicate URLs (engines[], positions[], content, title).
 *   4. Score each merged result using SearXNG's calculate_score algorithm.
 *   5. Sort by score descending.
 *
 * Aligned with SPEC.md §4 (Score Algorithm).
 */

import { EngineResponse, SearchResult, RawResult } from '../types.js';
import { normalizeUrl } from '../utils/url-utils.js';

/** Internal accumulator used while deduplicating. */
interface MergedAccumulator {
  title: string;
  url: string;
  content: string;
  engines: string[];
  positions: number[];
  publishedDate?: string;
  thumbnail?: string;
  category: string;
}

export class ResultMerger {
  constructor(private engineWeights: Record<string, number> = {}) {}

  /**
   * Merge multiple engine responses into a single sorted list of SearchResults.
   *
   * Algorithm:
   * 1. Iterate over every successful EngineResponse.
   * 2. Normalise each RawResult's URL (strip hash, tracking params).
   * 3. Use the normalised URL as a Map key; accumulate into MergedAccumulator.
   * 4. Convert accumulators → SearchResult and calculate SearXNG score.
   * 5. Sort by score descending.
   */
  merge(responses: EngineResponse[]): SearchResult[] {
    const urlMap = new Map<string, MergedAccumulator>();

    for (const response of responses) {
      if (!response.success || response.results.length === 0) {
        continue;
      }

      const engineName = response.engineName;

      for (const raw of response.results) {
        const normalisedUrl = normalizeUrl(raw.url, { forceHttp: false, stripAmp: false });
        const existing = urlMap.get(normalisedUrl);

        if (existing) {
          // --- Deduplication: merge into existing accumulator ---
          if (!existing.engines.includes(engineName)) {
            existing.engines.push(engineName);
          }
          existing.positions.push(raw.position ?? 0);

          // Prefer the longer title and content (heuristic for quality).
          if (raw.title && raw.title.length > existing.title.length) {
            existing.title = raw.title;
          }
          if (raw.content && raw.content.length > existing.content.length) {
            existing.content = raw.content;
          }

          // Keep the first publishedDate / thumbnail we see if not already set.
          if (raw.publishedDate && !existing.publishedDate) {
            existing.publishedDate = raw.publishedDate;
          }
          if (raw.thumbnail && !existing.thumbnail) {
            existing.thumbnail = raw.thumbnail;
          }

          // Prefer HTTPS over HTTP.
          if (raw.url.startsWith('https:') && existing.url.startsWith('http:')) {
            existing.url = raw.url;
          }
        } else {
          // --- First time seeing this URL ---
          urlMap.set(normalisedUrl, {
            title: raw.title ?? '',
            url: raw.url,
            content: raw.content ?? '',
            engines: [engineName],
            positions: [raw.position ?? 0],
            publishedDate: raw.publishedDate,
            thumbnail: raw.thumbnail,
            category: 'general',
          });
        }
      }
    }

    // Convert accumulators to SearchResult[], calculate scores, and sort.
    const merged: SearchResult[] = [];
    for (const acc of urlMap.values()) {
      const result: SearchResult = {
        title: acc.title,
        url: acc.url,
        content: acc.content || undefined,
        engine: acc.engines[0],
        engines: acc.engines,
        score: 0, // calculated below
        publishedDate: acc.publishedDate,
        category: acc.category,
        thumbnail: acc.thumbnail,
        positions: acc.positions,
      };

      result.score = this.calculateScore(result);
      merged.push(result);
    }

    // Sort by score descending (highest score first).
    merged.sort((a, b) => b.score - a.score);

    return merged;
  }

  // ---------------------------------------------------------------------------
  // Scoring – exact translation of SearXNG results.py calculate_score()
  // ---------------------------------------------------------------------------

  /**
   * Calculate the SearXNG score for a deduplicated result.
   *
   * Formula:
   *   weight = product(all engine weights) * count(positions)
   *   score  = sum(weight / position) for each position
   */
  private calculateScore(result: SearchResult): number {
    let weight = 1.0;
    for (const eng of result.engines ?? []) {
      weight *= this.engineWeights[eng] ?? 1.0;
    }
    weight *= (result.positions ?? []).length;

    let score = 0;
    for (const position of result.positions ?? []) {
      score += weight / position;
    }
    return score;
  }

}
