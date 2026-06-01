/**
 * Preset configurations — from conservative to unlimited.
 *
 * All presets have retryCount=0 because retries waste time budget.
 */

import type { PresetConfig } from './types.js';

/** Fast: 10 targets in ~15s */
export const FAST_PRESET: PresetConfig = {
  name: 'fast',
  concurrency: 8,
  perUrlTimeoutMs: 3000,
  connectTimeoutMs: 1000,
  hardTimeLimitMs: 15000,
  maxTargets: 10,
  maxTextCharsPerPage: 8000,
  retryCount: 0,
  streamLimitBytes: 100 * 1024,
  batchSize: 10,
  useWorkerPool: false,
  workerThreads: 2,
  extractEngine: 'fast',
  minContentChars: 200,
  minWordCount: 50,
  minSentenceCount: 3,
} as const;

/** Balanced: 20 targets in ~30s */
export const BALANCED_PRESET: PresetConfig = {
  name: 'balanced',
  concurrency: 25,
  perUrlTimeoutMs: 2500,
  connectTimeoutMs: 800,
  hardTimeLimitMs: 30000,
  maxTargets: 20,
  maxTextCharsPerPage: 15000,
  retryCount: 0,
  streamLimitBytes: 200 * 1024,
  batchSize: 20,
  useWorkerPool: true,
  workerThreads: 4,
  extractEngine: 'hybrid',
  minContentChars: 200,
  minWordCount: 50,
  minSentenceCount: 3,
} as const;

/** Deep: 50 targets in ~90s */
export const DEEP_PRESET: PresetConfig = {
  name: 'deep',
  concurrency: 50,
  perUrlTimeoutMs: 5000,
  connectTimeoutMs: 1000,
  hardTimeLimitMs: 90000,
  maxTargets: 50,
  maxTextCharsPerPage: 30000,
  retryCount: 0,
  streamLimitBytes: 300 * 1024,
  batchSize: 50,
  useWorkerPool: true,
  workerThreads: 6,
  extractEngine: 'readability',
  minContentChars: 200,
  minWordCount: 50,
  minSentenceCount: 3,
} as const;

/** Ultra: 50 targets in ~5s (the 5-second challenge) */
export const ULTRA_PRESET: PresetConfig = {
  name: 'ultra',
  concurrency: 100,
  perUrlTimeoutMs: 2000,
  connectTimeoutMs: 500,
  hardTimeLimitMs: 5000,
  maxTargets: 50,
  maxTextCharsPerPage: 15000,
  retryCount: 0,
  streamLimitBytes: 200 * 1024,
  batchSize: 50,
  useWorkerPool: true,
  workerThreads: 8,
  extractEngine: 'fast',
  minContentChars: 100,
  minWordCount: 30,
  minSentenceCount: 2,
} as const;

/** Maximum: 500 targets in ~10s */
export const MAXIMUM_PRESET: PresetConfig = {
  name: 'maximum',
  concurrency: 200,
  perUrlTimeoutMs: 1500,
  connectTimeoutMs: 400,
  hardTimeLimitMs: 10000,
  maxTargets: 500,
  maxTextCharsPerPage: 15000,
  retryCount: 0,
  streamLimitBytes: 150 * 1024,
  batchSize: 100,
  useWorkerPool: true,
  workerThreads: 8,
  extractEngine: 'fast',
  minContentChars: 100,
  minWordCount: 30,
  minSentenceCount: 2,
} as const;

/** Unlimited: 5000+ targets — bounded only by hardware */
export const UNLIMITED_PRESET: PresetConfig = {
  name: 'unlimited',
  concurrency: 500,
  perUrlTimeoutMs: 1000,
  connectTimeoutMs: 300,
  hardTimeLimitMs: 30000,
  maxTargets: 5000,
  maxTextCharsPerPage: 10000,
  retryCount: 0,
  streamLimitBytes: 100 * 1024,
  batchSize: 100,
  useWorkerPool: true,
  workerThreads: 16,
  extractEngine: 'fast',
  minContentChars: 50,
  minWordCount: 10,
  minSentenceCount: 1,
} as const;

// ─── Preset Registry ────────────────────────────────────────────

export const PRESETS: Record<string, PresetConfig> = {
  fast: FAST_PRESET,
  balanced: BALANCED_PRESET,
  deep: DEEP_PRESET,
  ultra: ULTRA_PRESET,
  maximum: MAXIMUM_PRESET,
  unlimited: UNLIMITED_PRESET,
} as const;

/**
 * Resolve a preset by name. Falls back to balanced if unknown.
 */
export function resolvePreset(name?: string): PresetConfig {
  if (!name) return BALANCED_PRESET;
  return PRESETS[name] ?? BALANCED_PRESET;
}

/**
 * Merge preset with user overrides.
 * User values always win (unbounded override).
 */
export function mergePreset(
  preset: PresetConfig,
  overrides: Record<string, number | boolean | string | undefined>,
): PresetConfig {
  const merged = { ...preset } as Record<string, unknown>;
  for (const [key, value] of Object.entries(overrides)) {
    if (value !== undefined && value !== null) {
      merged[key] = value;
    }
  }
  return merged as unknown as PresetConfig;
}
