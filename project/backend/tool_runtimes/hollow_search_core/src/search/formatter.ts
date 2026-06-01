/**
 * JSON response formatter – assembles the final SearchResponse payload.
 *
 * Aligned with SPEC.md §3 (SearchResponse type) and §10 (API Endpoints).
 *
 * The output mirrors SearXNG's JSON format:
 *   {
 *     "query": "...",
 *     "numberOfResults": 42,
 *     "results": [ ... ],
 *     "timing": { "brave": 123, "bing": 456 },
 *     "unresponsiveEngines": [ "duckduckgo" ]
 *   }
 */

import { SearchResult, SearchResponse } from '../types.js';

export class SearchResponseFormatter {
  /**
   * Build a SearchResponse object from the merged results and metadata.
   *
   * @param query                – the original user query string
   * @param results              – merged & scored SearchResult list
   * @param timing               – per-engine response times in milliseconds
   * @param unresponsiveEngines  – list of engine names that failed or timed out
   */
  format(
    query: string,
    results: SearchResult[],
    timing: Record<string, number>,
    unresponsiveEngines: string[],
  ): SearchResponse {
    return {
      query,
      numberOfResults: results.length,
      results,
      timing,
      unresponsiveEngines,
    };
  }
}
