// ============================================================================
// web-search — Content Processor: dedup, score, select
//
// Pure local algorithms:
//  1. Content-level deduplication (similarity-based)
//  2. Relevance scoring against query
//  3. Select best passages within maxContentLength budget
// ============================================================================

import type { CrawlResult, ProcessedPassage, MergedUrl } from './types.js';

// ─── Text Tokenization ─────────────────────────────────────────────────────

function tokenize(text: string): Set<string> {
  const words = text
    .toLowerCase()
    .replace(/[^\w\s]/g, ' ')
    .split(/\s+/)
    .filter((w) => w.length > 1);
  return new Set(words);
}

// ─── Content Deduplication ─────────────────────────────────────────────────

/**
 * Remove near-duplicate content using Jaccard similarity.
 * Two pages are considered duplicates if Jaccard similarity > 0.7.
 */
export function deduplicate(
  results: CrawlResult[],
  mergedUrls: MergedUrl[],
  threshold = 0.7,
): { kept: CrawlResult[]; removed: number } {
  const scored = results
    .filter((r) => r.status === 'success' && r.text.length > 100)
    .map((r) => {
      const mu = mergedUrls.find(
        (m) => normalizeUrlCompare(m.url, r.url),
      );
      return {
        ...r,
        _score: mu?.score ?? 0,
        _engines: mu?.engines ?? [],
      };
    });

  // Sort by search score descending (higher-scored results kept first)
  scored.sort((a, b) => (b._score as number) - (a._score as number));

  const kept: CrawlResult[] = [];
  const tokenSets: Array<{ tokens: Set<string>; result: CrawlResult }> = [];

  for (const r of scored) {
    const tokens = tokenize(r.text);
    if (tokens.size < 20) continue; // too short, skip

    let isDuplicate = false;
    for (const existing of tokenSets) {
      const intersection = new Set(
        [...tokens].filter((t) => existing.tokens.has(t)),
      );
      const union = new Set([...tokens, ...existing.tokens]);
      const similarity = intersection.size / union.size;

      if (similarity > threshold) {
        isDuplicate = true;
        break;
      }
    }

    if (!isDuplicate) {
      tokenSets.push({ tokens, result: r });
      kept.push(r);
    }
  }

  return { kept, removed: scored.length - kept.length };
}

function normalizeUrlCompare(a: string, b: string): boolean {
  try {
    const ua = new URL(a);
    const ub = new URL(b);
    ua.hash = '';
    ub.hash = '';
    return ua.toString() === ub.toString();
  } catch {
    return a === b;
  }
}

// ─── Relevance Scoring ─────────────────────────────────────────────────────

/**
 * Score each passage against the query using TF-IDF-like relevance.
 *
 * Formula:
 *   base = (matched key terms / total key terms) * term density bonus
 *   bonus = title match bonus (+0.2), snippet match bonus (+0.1)
 */
export function scoreRelevance(query: string, results: CrawlResult[], mergedUrls: MergedUrl[]): (CrawlResult & { score: number })[] {
  const queryTerms = query
    .toLowerCase()
    .split(/\s+/)
    .filter((w) => w.length > 1);

  const querySet = new Set(queryTerms);

  return results.map((r) => {
    const mu = mergedUrls.find((m) => normalizeUrlCompare(m.url, r.url));

    if (!r.text || r.text.length < 50) {
      return { ...r, score: 0 };
    }

    const lowerText = r.text.toLowerCase();
    const lowerTitle = (r.title || '').toLowerCase();

    // Term frequency: how many query terms appear in the text
    let matchCount = 0;
    for (const term of queryTerms) {
      if (lowerText.includes(term)) matchCount++;
    }
    const recall = queryTerms.length > 0 ? matchCount / queryTerms.length : 0;

    // Density: how many occurrences per 1000 chars
    let totalOccurrences = 0;
    for (const term of queryTerms) {
      const regex = new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      const matches = lowerText.match(regex);
      totalOccurrences += matches ? matches.length : 0;
    }
    const density = totalOccurrences / Math.max(r.text.length / 1000, 1);

    // Title bonus
    const titleBonus = queryTerms.some((t) => lowerTitle.includes(t)) ? 0.2 : 0;

    // Engine boost (URLs found by multiple engines)
    const engineBoost = Math.min(((mu?.engines?.length ?? 1) - 1) * 0.05, 0.15);

    // Position boost (higher position in search = more relevant)
    const positionBoost =
      mu?.positions && mu.positions.length > 0
        ? Math.max(0, 0.1 - Math.min(...mu.positions) * 0.01)
        : 0;

    const score = Math.min(
      recall * 0.5 + density * 0.2 + titleBonus + engineBoost + positionBoost,
      1.0,
    );

    return { ...r, score };
  });
}

// ─── Passage Selection ─────────────────────────────────────────────────────

/**
 * Select best passages within total content length budget.
 *
 * Strategy: greedy selection by score, ensuring diversity
 * (max 2 passages per domain).
 */
export function selectBest(
  scored: (CrawlResult & { score: number })[],
  mergedUrls: MergedUrl[],
  maxContentLength: number,
): ProcessedPassage[] {
  // Sort by score descending
  const sorted = [...scored].sort((a, b) => b.score - a.score);

  const selected: ProcessedPassage[] = [];
  const domainCount = new Map<string, number>();
  let totalChars = 0;

  for (const r of sorted) {
    if (r.score < 0.05) continue; // too irrelevant
    if (totalChars >= maxContentLength) break;

    const mu = mergedUrls.find((m) => normalizeUrlCompare(m.url, r.url));
    const domain = extractDomain(r.url);
    const domainCnt = domainCount.get(domain) || 0;

    // Max 2 per domain for diversity
    if (domainCnt >= 2) continue;

    // Truncate if this passage would exceed the budget
    let text = r.text;
    const remaining = maxContentLength - totalChars;
    if (text.length > remaining) {
      text = text.slice(0, remaining);
    }

    selected.push({
      url: r.url,
      title: r.title,
      text,
      score: r.score,
      domain,
      engine: mu?.engines?.[0] || 'unknown',
      engines: mu?.engines || [],
      wordCount: text.split(/\s+/).filter((w) => w.length > 0).length,
    });

    domainCount.set(domain, domainCnt + 1);
    totalChars += text.length;
  }

  return selected;
}

// ─── Helpers ───────────────────────────────────────────────────────────────

function extractDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return 'unknown';
  }
}
