// Engine Adapter base class and HTTP response types
// Aligned with SPEC.md Section 5

import { SearchRequest, RawResult, RequestParams } from '../types.js';

/**
 * HTTP response wrapper returned by fetchEngine in the orchestrator.
 * Mimics the subset of Response methods used by engine parsers.
 */
export interface EngineResponse {
  status: number;
  text(): Promise<string>;
  json(): Promise<unknown>;
  headers: Record<string, string>;
  url: string;
}

/**
 * Abstract base class for all search engine adapters.
 * Each engine implements:
 *   - buildRequest(): construct URL/headers/cookies from the query
 *   - parseResponse(): extract RawResult[] from the HTTP response
 */
export abstract class EngineAdapter {
  /** Engine identifier, e.g. "brave" */
  abstract readonly name: string;

  /** Engine configuration (weight, timeout, categories, etc.) */
  abstract readonly config: {
    name: string;
    shortcut: string;
    disabled: boolean;
    weight: number;
    timeout: number;
    categories: string[];
  };

  /**
   * Build the outgoing HTTP request parameters.
   * Called by the orchestrator before fetchEngine().
   */
  abstract buildRequest(query: string, req: SearchRequest): RequestParams;

  /**
   * Parse the HTTP response into a list of RawResult items.
   * Called by the orchestrator after fetchEngine() returns.
   */
  abstract parseResponse(resp: EngineResponse, params: RequestParams): Promise<RawResult[]>;
}
