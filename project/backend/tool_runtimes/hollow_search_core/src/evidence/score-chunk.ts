/**
 * Chunk scoring — relevance, information density, and noise penalty.
 *
 * v0.1 heuristic scoring without external models.
 *
 * @module score-chunk
 */

import { DEFAULT_OPTIONS, type Chunk, type EvidencePackOptions, type ScoredChunk } from './types.js';

const STOP_WORDS = new Set([
  'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
  'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
  'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'to', 'of',
  'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through',
  'during', 'before', 'after', 'above', 'below', 'between', 'under',
  'over', 'again', 'further', 'then', 'once', 'here', 'there', 'when',
  'where', 'why', 'how', 'all', 'both', 'each', 'few', 'more', 'most',
  'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same',
  'so', 'than', 'too', 'very',
  'and', 'but', 'or', 'yet', 'if', 'because', 'although', 'while',
  'that', 'which', 'who', 'what', 'this', 'these', 'those',
  'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
  'my', 'your', 'his', 'its', 'our', 'their',
]);

/**
 * Extract search terms from a query, removing stop words and punctuation.
 */
export function extractTerms(query: string): string[] {
  if (!query || query.trim().length === 0) return [];

  return query
    .toLowerCase()
    // Keep Unicode letters, numbers, and CJK characters; remove ASCII punctuation
    .replace(/[\x00-\x2F\x3A-\x40\x5B-\x60\x7B-\x7F]+/g, ' ')
    .split(/\s+/)
    .filter(t => {
      if (t.length === 0) return false;
      if (t.length === 1 && /^[a-z]$/.test(t)) return false; // single ASCII letter
      return !STOP_WORDS.has(t);
    });
}

// ---- relevance -----------------------------------------------------------

function calculateRelevance(queryTerms: string[], chunkText: string): number {
  const chunkLower = chunkText.toLowerCase();

  let matchedTerms = 0;
  let weightedScore = 0;

  for (const term of queryTerms) {
    const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(escaped, 'g');
    const matches = (chunkLower.match(regex) || []).length;
    if (matches > 0) {
      matchedTerms++;
      weightedScore += Math.log(1 + matches);
    }
  }

  // Coverage (60%)
  const coverage = queryTerms.length > 0 ? matchedTerms / queryTerms.length : 0;

  // Weighted frequency (30%), clamped to [0,1]
  const weightedFreq = Math.min(1, weightedScore / Math.max(1, queryTerms.length * 2));

  // Position boost (10%): any query term appears in first 30% of chunk
  const positionBoost = queryTerms.some(term => {
    const idx = chunkLower.indexOf(term);
    return idx >= 0 && idx < chunkText.length * 0.3;
  }) ? 0.1 : 0;

  return Math.min(1, coverage * 0.6 + weightedFreq * 0.3 + positionBoost);
}

// ---- density -------------------------------------------------------------

const DENSITY_RULES = [
  { pattern: /\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b/, score: 2 },
  { pattern: /\b\d+[\.,]?\d*%?\b/g, score: 1, limit: 3 },
  { pattern: /v?\d+\.\d+(\.\d+)?/, score: 1 },
  { pattern: /(结论是|结果表明|因此|所以|意味着)/, score: 3 },
  { pattern: /(因为|由于|导致|引起|造成)/, score: 2 },
  { pattern: /(是指|定义为|即|也就是说)/, score: 2 },
  { pattern: /[A-Z][a-z]+[A-Z]/, score: 1 },
  { pattern: /(声明|公告|official\s+statement|announced)/i, score: 3 },
  { pattern: /(https?:\/\/|et\s+al\.|DOI|arXiv)/i, score: 1 },
];

function calculateDensity(text: string): number {
  let rawScore = 0;

  for (const rule of DENSITY_RULES) {
    const matches = text.match(rule.pattern);
    if (matches) {
      const count = rule.limit ? Math.min(matches.length, rule.limit) : 1;
      rawScore += count * rule.score;
    }
  }

  return Math.min(1, rawScore / 10);
}

// ---- noise penalty -------------------------------------------------------

function calculateNoisePenalty(text: string): number {
  const lower = text.toLowerCase();

  // Complete noise — return immediately
  if (/(cookie|cookies)\s*consent/i.test(text)) return -5;
  if (/(log\s*in|sign\s*in|subscribe)\s*to/i.test(text)) return -5;
  if ((/©\s*\d{4}|all\s*rights\s*reserved/i.test(text)) && text.length < 200) return -5;

  let penalty = 0;

  if (/(sponsored|advertisement|promotion)/i.test(text)) penalty -= 3;
  if (/(related\s*articles?|you\s*may\s*also|recommended)/i.test(text)) penalty -= 3;

  const lines = text.split('\n').filter(l => l.trim());
  if (lines.length > 0 && lines.every(l => l.trim().length < 30 && /^[\s\-•*]/.test(l.trim()))) {
    penalty -= 2;
  }

  if (text.length < 100) penalty -= 2;

  const adjMatches = text.match(/\b(very|really|amazing|incredible|best|great|fantastic|excellent)\b/gi);
  if (adjMatches && adjMatches.length / (text.length / 100) > 0.5) {
    penalty -= 1;
  }

  return Math.max(-5, penalty);
}

// ---- match reason --------------------------------------------------------

function buildMatchReason(matchedTerms: number, totalTerms: number, density: number): string {
  const parts: string[] = [];
  if (matchedTerms > 0) parts.push(`${matchedTerms}/${totalTerms} terms matched`);
  if (density > 0.5) parts.push('high info density');
  else if (density > 0.2) parts.push('medium info density');
  return parts.join(', ');
}

// ---- public API ----------------------------------------------------------

/**
 * Score a single chunk against a query.
 */
export function scoreChunk(
  query: string,
  chunk: Chunk,
  options: EvidencePackOptions = {},
): ScoredChunk {
  const queryTerms = extractTerms(query);

  const relevanceScore = calculateRelevance(queryTerms, chunk.text);
  const densityScore = calculateDensity(chunk.text);
  const noisePenalty = calculateNoisePenalty(chunk.text);
  const relevanceWeight = options.relevanceWeight ?? DEFAULT_OPTIONS.relevanceWeight ?? 0.7;
  const densityWeight = options.densityWeight ?? DEFAULT_OPTIONS.densityWeight ?? 0.3;

  const combinedScore = Math.max(
    0,
    relevanceScore * relevanceWeight + densityScore * densityWeight + noisePenalty,
  );

  // Count matched terms for matchReason
  const chunkLower = chunk.text.toLowerCase();
  let matchedTerms = 0;
  for (const term of queryTerms) {
    if (chunkLower.includes(term)) matchedTerms++;
  }

  return {
    ...chunk,
    relevanceScore,
    densityScore,
    noisePenalty,
    combinedScore,
    matchReason: buildMatchReason(matchedTerms, queryTerms.length, densityScore),
  };
}

/**
 * Score all chunks in parallel.
 */
export function scoreAllChunks(
  query: string,
  chunks: Chunk[],
  options: EvidencePackOptions = {},
): ScoredChunk[] {
  return chunks.map(chunk => scoreChunk(query, chunk, options));
}
