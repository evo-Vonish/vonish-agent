// ============================================================================
// web-search — Text Extraction & Cleaning
//
// Fast cheerio-based extraction (no JSDOM overhead).
// Strategy: find the largest text block (article > main > div+p > body).
// ============================================================================

import * as cheerio from 'cheerio';
import type { CrawlResult } from './types.js';

// ─── HTML Entity Decoder ───────────────────────────────────────────────────

const HTML_ENTITIES: Record<string, string> = {
  '&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>',
  '&quot;': '"', '&#39;': "'", '&ndash;': '-', '&mdash;': '-',
  '&hellip;': '...', '&copy;': '©', '&reg;': '®', '&trade;': '™',
};

// ─── Text Cleaning ─────────────────────────────────────────────────────────

const NOISE_PATTERNS = [
  /cookie\s*(consent|notice|policy)/i,
  /(accept|decline)\s*(all\s*)?cookies?/i,
  /privacy\s*(policy|notice|settings)/i,
  /advertisement|sponsored\s*content/i,
  /subscribe\s*(now|today|for\s*free)/i,
  /sign\s*(up|in)\s*(now|today|here)/i,
  /(click|tap)\s*here\s*(to|for)/i,
  /download\s*(our\s*)?app/i,
  /read\s*more\s*(\.{3}|…)/i,
  /^share\s*(this|on|to)\s*/i,
  /^follow\s*(us|me)\s*/i,
  /^comments?\s*\(?\d*\)?\s*$/i,
  /leave\s*a\s*(comment|reply)/i,
  /^posted\s*(by|on|in)\s*/i,
  /all\s*rights?\s*reserved/i,
  /copyright\s*©?\s*\d{4}/i,
  /^back\s*to\s*top$/i,
];

function cleanText(raw: string): string {
  if (!raw) return '';

  let text = raw;

  // Decode HTML entities
  for (const [entity, ch] of Object.entries(HTML_ENTITIES)) {
    text = text.split(entity).join(ch);
  }
  text = text.replace(/&#\d+;/g, ' ');

  // Remove control characters
  text = text.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]+/g, '');

  // Normalize whitespace
  text = text.replace(/[ \t]+/g, ' ');

  // Collapse 3+ newlines into 2
  text = text.replace(/\n{3,}/g, '\n\n');

  // Filter noise lines
  const lines = text.split('\n').filter((line) => {
    const trimmed = line.trim();
    if (trimmed.length < 4) return false;
    return !NOISE_PATTERNS.some((p) => p.test(trimmed));
  });

  return lines.join('\n').trim();
}

// ─── Fast Content Extraction ───────────────────────────────────────────────

interface Extracted {
  title: string;
  text: string;
  excerpt: string;
  wordCount: number;
  charCount: number;
}

export function extractContent(html: string, url: string): Extracted {
  const $ = cheerio.load(html);

  // Remove noise elements
  $('script, style, nav, footer, header, iframe, aside, .sidebar, ' +
    '.advertisement, .ad, noscript, .cookie-banner, .cookie-consent, ' +
    '[role="navigation"], [role="banner"], [role="contentinfo"]').remove();

  // Extract title
  let title =
    $('title').text().trim() ||
    $('h1').first().text().trim() ||
    $('meta[property="og:title"]').attr('content')?.trim() ||
    '';

  // Find the best content block
  const candidates: Array<{ text: string; wordCount: number }> = [];

  // Candidate 1: <article>
  $('article').each((_i, el) => {
    const t = $(el).text().trim();
    if (t.length > 50) {
      candidates.push({ text: t, wordCount: t.split(/\s+/).length });
    }
  });

  // Candidate 2: <main>
  $('main').each((_i, el) => {
    const t = $(el).text().trim();
    if (t.length > 50) {
      candidates.push({ text: t, wordCount: t.split(/\s+/).length });
    }
  });

  // Candidate 3: div with 2+ paragraphs
  $('div').each((_i, el) => {
    const pCount = $(el).find('p').length;
    if (pCount >= 2) {
      const t = $(el).text().trim();
      if (t.length > 50) {
        candidates.push({ text: t, wordCount: t.split(/\s+/).length });
      }
    }
  });

  // Candidate 4: <body> fallback
  const bodyText = $('body').text().trim();
  if (bodyText.length > 20) {
    candidates.push({ text: bodyText, wordCount: bodyText.split(/\s+/).length });
  }

  // Pick candidate with most words
  let bestText = '';
  let bestWords = 0;
  for (const c of candidates) {
    if (c.wordCount > bestWords) {
      bestWords = c.wordCount;
      bestText = c.text;
    }
  }

  // Clean
  const text = cleanText(bestText);
  const words = text.split(/\s+/).filter((w) => w.length > 0);

  return {
    title: title || url,
    text,
    excerpt: text.slice(0, 200),
    wordCount: words.length,
    charCount: text.length,
  };
}

// ─── Batch Extract ─────────────────────────────────────────────────────────

/**
 * Extract text from all successfully crawled pages.
 * Returns enriched CrawlResults.
 */
export function extractAll(
  crawlResults: CrawlResult[],
  maxPerUrl: number,
): CrawlResult[] {
  return crawlResults.map((cr) => {
    if (cr.status !== 'success' || !cr.text) {
      return cr;
    }

    try {
      const extracted = extractContent(cr.text, cr.url);
      const truncated = extracted.text.slice(0, maxPerUrl);

      return {
        ...cr,
        title: extracted.title || cr.title,
        text: truncated,
        charCount: truncated.length,
        wordCount: truncated.split(/\s+/).filter((w) => w.length > 0).length,
      };
    } catch {
      return { ...cr, status: 'failed', text: '', wordCount: 0, charCount: 0 };
    }
  });
}
