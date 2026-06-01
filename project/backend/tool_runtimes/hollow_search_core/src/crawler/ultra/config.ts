/**
 * Configuration resolver — merge preset + user overrides.
 */

import type { UltraCrawlOptions, ResolvedCrawlOptions } from './types.js';
import { resolvePreset, mergePreset } from './presets.js';

/**
 * Resolve all options by merging preset defaults with user overrides.
 * User values always take precedence (unbounded).
 */
export function resolveOptions(opts: UltraCrawlOptions): ResolvedCrawlOptions {
  const preset = resolvePreset(opts.preset);

  // Build overrides map from user options
  const overrides: Record<string, number | boolean | string | undefined> = {};

  if (opts.concurrency !== undefined) overrides.concurrency = opts.concurrency;
  if (opts.perUrlTimeoutMs !== undefined) overrides.perUrlTimeoutMs = opts.perUrlTimeoutMs;
  if (opts.connectTimeoutMs !== undefined) overrides.connectTimeoutMs = opts.connectTimeoutMs;
  if (opts.hardTimeLimitMs !== undefined) overrides.hardTimeLimitMs = opts.hardTimeLimitMs;
  if (opts.maxTargets !== undefined) overrides.maxTargets = opts.maxTargets;
  if (opts.maxTextCharsPerPage !== undefined)
    overrides.maxTextCharsPerPage = opts.maxTextCharsPerPage;
  if (opts.retryCount !== undefined) overrides.retryCount = opts.retryCount;
  if (opts.streamLimitBytes !== undefined) overrides.streamLimitBytes = opts.streamLimitBytes;
  if (opts.batchSize !== undefined) overrides.batchSize = opts.batchSize;
  if (opts.useWorkerPool !== undefined) overrides.useWorkerPool = opts.useWorkerPool;
  if (opts.workerThreads !== undefined) overrides.workerThreads = opts.workerThreads;
  if (opts.extractEngine !== undefined) overrides.extractEngine = opts.extractEngine;
  if (opts.minContentChars !== undefined) overrides.minContentChars = opts.minContentChars;
  if (opts.minWordCount !== undefined) overrides.minWordCount = opts.minWordCount;
  if (opts.minSentenceCount !== undefined) overrides.minSentenceCount = opts.minSentenceCount;

  const merged = mergePreset(preset, overrides);

  return {
    ...merged,
    mode: opts.mode,
    preset: opts.preset || preset.name,
    query: opts.query || '',
    urls: opts.urls || [],
    onBatch: opts.onBatch,
    onProgress: opts.onProgress,
    userAgent: opts.userAgent,
    removeDuplicates: opts.removeDuplicates ?? true,
    maxPerDomain: opts.maxPerDomain,
  } as ResolvedCrawlOptions;
}
