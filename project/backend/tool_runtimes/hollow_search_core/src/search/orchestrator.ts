/**
 * Engine parallel orchestrator – the heart of Mini-SearXNG.
 *
 * Translates the concurrency model from SearXNG's search/__init__.py:
 *   - Every enabled engine is launched simultaneously.
 *   - Each engine carries its own timeout (Promise.race + timer).
 *   - Promise.allSettled guarantees that one engine failing or timing out
 *     never disrupts the others.
 *   - Response time (elapsedMs) is recorded for every attempt.
 *
 * Aligned with SPEC.md §7 (Orchestrator Design).
 */

import {
  SearchRequest,
  EngineResponse,
} from '../types.js';
import { EngineAdapter } from '../engines/engine.js';
import { HttpClient } from '../utils/http-client.js';

/** Sleep helper that rejects after `ms` milliseconds. */
function sleepReject(ms: number, message: string): Promise<never> {
  return new Promise((_resolve, reject) => {
    setTimeout(() => reject(new Error(message)), ms);
  });
}

export class EngineOrchestrator {
  constructor(
    private engines: EngineAdapter[],
    private defaultTimeout: number = 30000,
    private httpClient: HttpClient = new HttpClient(),
  ) {}

  /**
   * Execute the search request against all enabled engines in parallel.
   *
   * Steps:
   * 1. Filter the list of adapters based on `request.engines`.
   * 2. For each engine create a task that races between the actual search
   *    and an independent timeout.
   * 3. Wait for all tasks via Promise.allSettled.
   * 4. Collect success / failure into EngineResponse objects.
   */
  async execute(request: SearchRequest): Promise<EngineResponse[]> {
    const enabledEngines = this.getEnabledEngines(request.engines);

    if (enabledEngines.length === 0) {
      return [];
    }

    // Build a raced + timed task for every engine.
    const tasks = enabledEngines.map((engine) => {
      const effectiveTimeout = request.timeout ?? engine.config.timeout ?? this.defaultTimeout;

      const searchTask = this.searchOneEngine(engine, request);
      const timeoutTask = sleepReject(effectiveTimeout, `Engine "${engine.name}" timed out after ${effectiveTimeout}ms`);

      // Promise.race lets the engine finish early OR the timeout fire first.
      return Promise.race([searchTask, timeoutTask]).catch((err: Error): EngineResponse => ({
        results: [],
        engineName: engine.name,
        elapsedMs: effectiveTimeout,
        success: false,
        error: err.message,
      }));
    });

    // Wait for everything – no engine can break the others.
    const settled = await Promise.allSettled(tasks);

    // unwrap – all our tasks return EngineResponse directly, so status is always
    // 'fulfilled' in practice, but we normalise just in case.
    const responses: EngineResponse[] = settled.map((s) => {
      if (s.status === 'fulfilled') {
        return s.value;
      }
      // This path is defensive; the catch() above normally prevents rejections.
      const reason = s.reason instanceof Error ? s.reason.message : String(s.reason);
      return {
        results: [],
        engineName: 'unknown',
        elapsedMs: 0,
        success: false,
        error: reason,
      };
    });

    return responses;
  }

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  /** Return only the engines enabled by the user request. */
  private getEnabledEngines(requested?: string[]): EngineAdapter[] {
    if (!requested || requested.length === 0) {
      // Default: all non-disabled engines
      return this.engines.filter((e) => !e.config.disabled);
    }
    const names = new Set(requested.map((n) => n.toLowerCase()));
    return this.engines.filter((e) => names.has(e.name.toLowerCase()));
  }

  /** Execute a single engine end-to-end and record timing. */
  private async searchOneEngine(
    engine: EngineAdapter,
    request: SearchRequest,
  ): Promise<EngineResponse> {
    const startTime = performance.now();

    try {
      // 1. Build request parameters (URL, headers, cookies, method, body).
      const params = engine.buildRequest(request.query, request);

      // 2. Perform the actual HTTP fetch.
      const httpResp = await this.httpClient.request(params);

      // 3. Let the engine parse the response into RawResult items.
      const results = await engine.parseResponse(httpResp, params);

      const elapsedMs = Math.round(performance.now() - startTime);

      return {
        results,
        engineName: engine.name,
        elapsedMs,
        success: true,
      };
    } catch (err) {
      const elapsedMs = Math.round(performance.now() - startTime);
      const message = err instanceof Error ? err.message : String(err);

      return {
        results: [],
        engineName: engine.name,
        elapsedMs,
        success: false,
        error: message,
      };
    }
  }

}
