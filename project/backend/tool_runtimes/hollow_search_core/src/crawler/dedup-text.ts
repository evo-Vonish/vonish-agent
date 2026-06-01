/**
 * Two-pass deduplication utilities for crawled articles.
 *
 * Pass 1 – URL deduplication:  articles pointing at the same canonical URL
 *            (after normalisation) are collapsed to the first occurrence.
 *
 * Pass 2 – Content deduplication: articles with identical MD5 hashes of their
 *            normalised text are collapsed to the first occurrence.
 *
 * Dependencies: Node.js `crypto` module and `./types.js`.
 */

import { createHash } from 'crypto';
import { CrawledArticle } from './types.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * Query parameters that are removed during URL normalisation because they
 * carry tracking / campaign data and do not affect page content.
 */
const TRACKING_PARAMS = [
  'utm_source',
  'utm_medium',
  'utm_campaign',
  'utm_term',
  'utm_content',
  'utm_id',
  'utm_source_platform',
  'utm_creative_format',
  'utm_marketing_tactic',
  'fbclid',
  'gclid',
  'gbraid',
  'wbraid',
  'msclkid',
  'dclid',
  'twclid',
  'li_fat_id',
  'mc_cid',
  'mc_eid',
  '_ga',
  '_gid',
  '_gac',
  '_gl',
  'oly_anon_id',
  'oly_enc_id',
  'rb_clickid',
  's_kwcid',
  'ef_id',
  'epik',
  'pk_campaign',
  'pk_kwd',
  'pk_keyword',
  'pk_source',
  'pk_medium',
  'pk_content',
  'pk_cid',
  'piwik_campaign',
  'piwik_kwd',
  'piwik_keyword',
  'mtm_campaign',
  'mtm_source',
  'mtm_medium',
  'mtm_content',
  'mtm_cid',
  'mtm_group',
  'mtm_placement',
  'matomo_campaign',
  'matomo_source',
  'matomo_medium',
  'matomo_content',
  'matomo_cid',
  'matomo_group',
  'matomo_placement',
  'itm_source',
  'itm_medium',
  'itm_campaign',
  'itm_term',
  'itm_content',
];

// ---------------------------------------------------------------------------
// URL normalisation
// ---------------------------------------------------------------------------

/**
 * Normalise a URL for deduplication.
 *
 * Transformations applied (in order):
 * 1. Parse with the WHATWG `URL` constructor.
 * 2. Strip the fragment (`#…`).
 * 3. Remove known tracking query parameters (`utm_*`, `fbclid`, `gclid`, …).
 * 4. Collapse empty search string.
 * 5. Remove trailing slash unless the path is `/`.
 * 6. Force the protocol to `http:` (content is assumed identical).
 * 7. Remove `/amp/` or `/amp.` path segments (AMP variants).
 * 8. Re-serialise to string.
 *
 * If parsing fails the original string is returned unmodified – it will still
 * participate in deduplication, just under its raw form.
 *
 * @param url - Absolute or relative URL string.
 * @returns Normalised URL string suitable for use as a deduplication key.
 */
export function normalizeUrl(url: string): string {
  if (!url || typeof url !== 'string') {
    return '';
  }

  let parsed: URL;
  try {
    parsed = new URL(url.trim());
  } catch {
    // Malformed URL – return trimmed original as best-effort key.
    return url.trim();
  }

  // 2. Strip fragment
  parsed.hash = '';

  // 3. Remove tracking parameters
  for (const param of TRACKING_PARAMS) {
    parsed.searchParams.delete(param);
  }

  // 4. Collapse empty search string so it doesn't leave a trailing "?"
  if (parsed.search === '' || parsed.search === '?') {
    parsed.search = '';
  }

  // 5. Remove trailing slash (but keep root "/")
  if (parsed.pathname.length > 1 && parsed.pathname.endsWith('/')) {
    parsed.pathname = parsed.pathname.slice(0, -1);
  }

  // 6. Normalise protocol to http
  parsed.protocol = 'http:';

  // 7. Handle AMP links: remove "/amp/" or "/amp." segments
  parsed.pathname = parsed.pathname
    .replace(/\/amp\//g, '/')
    .replace(/\/amp\./g, '/');

  // Final clean-up: remove doubled slashes introduced by AMP removal
  parsed.pathname = parsed.pathname.replace(/\/+/g, '/');

  return parsed.toString();
}

// ---------------------------------------------------------------------------
// Content hashing
// ---------------------------------------------------------------------------

/**
 * Generate an MD5 hash of the *normalised* text for content deduplication.
 *
 * Normalisation steps:
 * - lower-case
 * - collapse all runs of whitespace to a single space
 * - trim
 * - keep at most the first 5 000 characters
 *
 * @param text - Raw or cleaned article text.
 * @returns 32-character hex MD5 digest.
 */
export function hashText(text: string): string {
  const normalized = text
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 5000);
  return createHash('md5').update(normalized).digest('hex');
}

// ---------------------------------------------------------------------------
// Deduplication
// ---------------------------------------------------------------------------

/** Result shape returned by {@link deduplicateArticles}. */
export interface DedupResult {
  /** Articles that survived both deduplication passes. */
  unique: CrawledArticle[];
  /** Number of articles removed by both URL and content-hash deduplication. */
  duplicatesRemoved: number;
}

/**
 * Deduplicate a list of crawled articles in two passes.
 *
 * **Pass 1 – URL deduplication:**
 * Articles whose {@link normalizeUrl | normalised URL} matches an article
 * already seen are dropped.  This pass does **not** contribute to
 * `duplicatesRemoved` because different URLs usually serve different content.
 *
 * **Pass 2 – Content deduplication:**
 * Articles whose `textHash` matches an article already kept from Pass 1 are
 * dropped.  The count of articles removed in this pass is reported as
 * `duplicatesRemoved`.
 *
 * @param articles - Array of crawled articles (order is preserved for keeps).
 * @returns Object containing the unique articles and the duplicate count.
 */
export function deduplicateArticles(articles: CrawledArticle[]): DedupResult {
  const urlMap = new Map<string, CrawledArticle>();
  const hashMap = new Map<string, CrawledArticle>();
  let duplicatesRemoved = 0;

  // Pass 1 – URL deduplication (normalizeUrl as key)
  const urlUnique: CrawledArticle[] = [];
  for (const article of articles) {
    const urlKey = normalizeUrl(article.url);
    if (urlMap.has(urlKey)) {
      duplicatesRemoved++;
      continue;
    }
    urlMap.set(urlKey, article);
    urlUnique.push(article);
  }

  // Pass 2 – Content deduplication (textHash as key)
  const unique: CrawledArticle[] = [];
  for (const article of urlUnique) {
    const hashKey = article.textHash;
    if (hashMap.has(hashKey)) {
      duplicatesRemoved++;
      continue;
    }
    hashMap.set(hashKey, article);
    unique.push(article);
  }

  return { unique, duplicatesRemoved };
}

// ---------------------------------------------------------------------------
// Similarity helpers (for future enhancements)
// ---------------------------------------------------------------------------

/**
 * Compute the Jaccard similarity between two title strings.
 *
 * Each title is split on non-word characters, lower-cased, and treated as a
 * set of tokens.  The similarity is the size of the intersection divided by
 * the size of the union.
 *
 * @returns A number in the range `[0, 1]` where `1` means identical sets.
 */
export function titleSimilarity(a: string, b: string): number {
  if (!a || !b) return 0;
  if (a === b) return 1;

  const setA = new Set(
    a
      .toLowerCase()
      .split(/[^\w\u00C0-\u024F\u1E00-\u1EFF]+/u)
      .filter((w) => w.length > 0),
  );
  const setB = new Set(
    b
      .toLowerCase()
      .split(/[^\w\u00C0-\u024F\u1E00-\u1EFF]+/u)
      .filter((w) => w.length > 0),
  );

  if (setA.size === 0 && setB.size === 0) return 0;

  let intersection = 0;
  for (const token of setA) {
    if (setB.has(token)) {
      intersection++;
    }
  }

  const union = setA.size + setB.size - intersection;
  return union === 0 ? 0 : intersection / union;
}
