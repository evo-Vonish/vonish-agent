/**
 * Chunk deduplication utilities.
 *
 * Removes exact and near-duplicate chunks using hash-based exact
 * dedup and Jaccard-similarity near-dedup.
 *
 * @module dedup-chunks
 */

import type { ScoredChunk, DedupOptions, DedupResult } from './types.js';

/**
 * Compute a simple hash of a string for exact dedup.
 *
 * @param text - Input string
 * @returns Simple hash string
 */
function hashText(text: string): string {
  let h = 0;
  for (let i = 0; i < text.length; i++) {
    h = ((h << 5) - h + text.charCodeAt(i)) | 0;
  }
  return h.toString(16);
}

/**
 * Compute Jaccard similarity between two strings using character bigrams.
 *
 * @param a - First string
 * @param b - Second string
 * @returns Jaccard similarity in [0, 1]
 */
function jaccardSimilarity(a: string, b: string): number {
  const bigramsA = new Set<string>();
  const bigramsB = new Set<string>();

  const la = a.length;
  const lb = b.length;

  if (la === 0 && lb === 0) return 1;
  if (la === 0 || lb === 0) return 0;

  for (let i = 0; i < la - 1; i++) {
    bigramsA.add(a.slice(i, i + 2));
  }
  for (let i = 0; i < lb - 1; i++) {
    bigramsB.add(b.slice(i, i + 2));
  }

  let intersection = 0;
  for (const bg of bigramsA) {
    if (bigramsB.has(bg)) intersection++;
  }

  const union = bigramsA.size + bigramsB.size - intersection;
  return union === 0 ? 0 : intersection / union;
}

/**
 * Remove exact and near-duplicate chunks.
 *
 * Keeps the highest-scoring chunk among duplicates.
 *
 * @param chunks - Array of scored chunks
 * @param options - Deduplication options
 * @returns DedupResult with unique chunks and counts
 */
export function dedupChunks(
  chunks: ScoredChunk[],
  options: DedupOptions,
): DedupResult {
  const { exactDedup, nearDedupThreshold } = options;

  let exactDuplicatesRemoved = 0;
  let nearDuplicatesRemoved = 0;

  // Work with a copy sorted by combined score descending (keep highest scored)
  const sorted = [...chunks].sort((a, b) => b.combinedScore - a.combinedScore);

  const uniqueChunks: ScoredChunk[] = [];
  const seenHashes = new Set<string>();

  for (const chunk of sorted) {
    // Exact dedup
    if (exactDedup) {
      const h = hashText(chunk.text);
      if (seenHashes.has(h)) {
        exactDuplicatesRemoved++;
        continue;
      }
      seenHashes.add(h);
    }

    // Near dedup: compare against already-kept chunks
    if (nearDedupThreshold < 1) {
      let isNearDup = false;
      for (const kept of uniqueChunks) {
        const sim = jaccardSimilarity(chunk.text, kept.text);
        if (sim >= nearDedupThreshold) {
          isNearDup = true;
          nearDuplicatesRemoved++;
          break;
        }
      }
      if (isNearDup) continue;
    }

    uniqueChunks.push(chunk);
  }

  // Restore original order by sourceId and startChar
  uniqueChunks.sort((a, b) => {
    if (a.sourceId !== b.sourceId) return a.sourceId.localeCompare(b.sourceId);
    return a.startChar - b.startChar;
  });

  return {
    uniqueChunks,
    exactDuplicatesRemoved,
    nearDuplicatesRemoved,
  };
}
