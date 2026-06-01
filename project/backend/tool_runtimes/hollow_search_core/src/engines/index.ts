// Engine adapters registry
// Exports all engine implementations and a factory function

import { EngineAdapter, EngineResponse } from './engine.js';
import { BraveEngine } from './brave.js';
import { BingEngine } from './bing.js';
import { DuckDuckGoEngine } from './duckduckgo.js';
import { WikipediaEngine } from './wikipedia.js';
import { GoogleEngine } from './google.js';
import { loadEngineConfigMap } from '../config.js';

export { EngineAdapter, EngineResponse };
export { BraveEngine };
export { BingEngine };
export { DuckDuckGoEngine };
export { WikipediaEngine };
export { GoogleEngine };

/**
 * Create a list of all default engine adapters.
 * Used by the orchestrator to initialize available search engines.
 */
export function createDefaultEngines(): EngineAdapter[] {
  const configs = loadEngineConfigMap();
  return [
    new BraveEngine(configs.get('brave')),
    new BingEngine(configs.get('bing')),
    new DuckDuckGoEngine(configs.get('duckduckgo')),
    new WikipediaEngine(configs.get('wikipedia')),
    new GoogleEngine(configs.get('google')),
  ];
}
