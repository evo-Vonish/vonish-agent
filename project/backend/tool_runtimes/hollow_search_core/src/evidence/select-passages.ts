/**
 * Passage selection utilities.
 *
 * Selects the best passages from scored chunks applying MMR
 * (Maximal Marginal Relevance) for diversity, along with
 * per-source and per-domain constraints.
 *
 * @module select-passages
 */

import type { ScoredChunk, SourcePassage, PassageSelectionOptions } from './types.js';

/**
 * Compute Jaccard similarity between two strings (character bigrams).
 *
 * @param a - First string
 * @param b - Second string
 * @returns Similarity in [0, 1]
 */
function similarity(a: string, b: string): number {
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
 * Select passages from scored chunks with diversity and constraint handling.
 *
 * Uses MMR for diversity and enforces per-source / per-domain limits.
 *
 * @param chunks - Array of scored (and deduplicated) chunks
 * @param domainMap - Map from sourceId to domain name
 * @param options - Selection constraints
 * @returns Array of selected source passages
 */
export function selectPassages(
  chunks: ScoredChunk[],
  domainMap: Map<string, string>,
  options: PassageSelectionOptions,
): SourcePassage[] {
  const { maxPassages, maxPerSource, maxPerDomain, mmrLambda = 0.5 } = options;

  if (chunks.length === 0) return [];

  // Sort by combined score descending
  const candidates = [...chunks].sort((a, b) => b.combinedScore - a.combinedScore);

  const selected: ScoredChunk[] = [];
  const sourceCounts = new Map<string, number>();
  const domainCounts = new Map<string, number>();

  while (selected.length < maxPassages && candidates.length > 0) {
    let bestIdx = -1;
    let bestScore = -Infinity;

    for (let i = 0; i < candidates.length; i++) {
      const candidate = candidates[i];
      const sourceId = candidate.sourceId;
      const domain = domainMap.get(sourceId) || 'unknown';

      // Check constraints
      const srcCount = sourceCounts.get(sourceId) || 0;
      if (srcCount >= maxPerSource) continue;

      const domCount = domainCounts.get(domain) || 0;
      if (domCount >= maxPerDomain) continue;

      // MMR score: lambda * relevance - (1 - lambda) * max_similarity_to_selected
      let maxSim = 0;
      for (const sel of selected) {
        const sim = similarity(candidate.text, sel.text);
        if (sim > maxSim) maxSim = sim;
      }

      const mmrScore = mmrLambda * candidate.combinedScore - (1 - mmrLambda) * maxSim;

      if (mmrScore > bestScore) {
        bestScore = mmrScore;
        bestIdx = i;
      }
    }

    if (bestIdx === -1) break;

    const chosen = candidates[bestIdx];
    selected.push(chosen);

    const chosenDomain = domainMap.get(chosen.sourceId) || 'unknown';
    sourceCounts.set(chosen.sourceId, (sourceCounts.get(chosen.sourceId) || 0) + 1);
    domainCounts.set(chosenDomain, (domainCounts.get(chosenDomain) || 0) + 1);

    candidates.splice(bestIdx, 1);
  }

  // Map to SourcePassage
  return selected.map((chunk, idx) => ({
    id: `passage_${(idx + 1).toString().padStart(3, '0')}`,
    sourceId: chunk.sourceId,
    chunkId: chunk.id,
    text: chunk.text,
    startChar: chunk.startChar,
    endChar: chunk.endChar,
    score: chunk.combinedScore,
    reason: chunk.matchReason,
  }));
}
