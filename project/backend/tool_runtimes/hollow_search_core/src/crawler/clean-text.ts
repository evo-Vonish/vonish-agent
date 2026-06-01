/**
 * Text cleaning utilities for crawled HTML content.
 *
 * This module sanitises raw text extracted from web pages by:
 * - decoding HTML entities
 * - stripping hidden / structural tags and their contents
 * - normalising whitespace
 * - removing advertisement / navigation noise
 * - discarding very short meaningless fragments
 *
 * It has **no external dependencies** and can be used independently of the
 * other crawler modules.
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** HTML entities that are replaced before any other processing. */
const HTML_ENTITIES: Record<string, string> = {
  '&nbsp;': ' ',
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&#39;': "'",
  '&apos;': "'",
  '&#x27;': "'",
  '&#x2F;': '/',
  '&#47;': '/',
  '&mdash;': '—',
  '&ndash;': '–',
  '&hellip;': '…',
  '&copy;': '©',
  '&reg;': '®',
  '&trade;': '™',
  '&ldquo;': '"',
  '&rdquo;': '"',
  '&lsquo;': "'",
  '&rsquo;': "'",
  '&#8211;': '–',
  '&#8212;': '—',
  '&#8230;': '…',
  '&#8220;': '"',
  '&#8221;': '"',
  '&#8216;': "'",
  '&#8217;': "'",
};

/** Tag names whose content is removed entirely (case-insensitive). */
const TAGS_TO_REMOVE = [
  'script',
  'style',
  'nav',
  'footer',
  'header',
  'aside',
  'noscript',
  'iframe',
  'svg',
  'canvas',
  'template',
  'form',
  'button',
  'input',
  'select',
  'textarea',
];

/** Regular expression matching any of the tags above (with content). */
const TAG_REMOVE_RE = new RegExp(
  `<(${TAGS_TO_REMOVE.join('|')})[^>]*>[\\s\\S]*?<\\/\\1>`,
  'gi',
);

/** Keywords that indicate an advertisement / UI line (case-insensitive). */
const AD_KEYWORDS = [
  'advertisement',
  'sponsored',
  'click here',
  'subscribe now',
  'sign up',
  'cookies',
  'privacy policy',
  'terms of service',
  'terms and conditions',
  'all rights reserved',
  'follow us on',
  'share this article',
  'related articles',
  'read more',
  'learn more',
  'download now',
  'get started',
  'buy now',
  'shop now',
  'limited time',
  'ad choices',
  'cookie policy',
];

/** Short text fragments that appear repeatedly in ads / navigation. */
const REPETITIVE_PATTERNS = [
  /^home$/i,
  /^next$/i,
  /^previous$/i,
  /^back$/i,
  /^menu$/i,
  /^search$/i,
  /^login$/i,
  /^log in$/i,
  /^register$/i,
  /^sign in$/i,
  /^logout$/i,
  /^log out$/i,
  /^close$/i,
  /^skip$/i,
  /^more$/i,
  /^continue$/i,
];

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Clean extracted text by removing invisible markup, ads, navigation noise,
 * and normalising whitespace.
 *
 * The function works in 8 ordered stages:
 *
 * 1. **Decode HTML entities** – `&nbsp;` → space, `&amp;` → `&`, …
 * 2. **Remove unwanted tags** – `<script>`, `<style>`, `<nav>`, `<footer>`, …
 * 3. **Collapse all consecutive whitespace** (including `\t`, `\n`, `\r`) to a
 *    single space.
 * 4. **Trim each line** and **collapse consecutive blank lines** to a single
 *    blank line.
 * 5. **Remove very short lines** (< 3 characters).
 * 6. **Remove repetitive UI patterns** ("Home", "Next", "Login", …).
 * 7. **Remove lines containing ad / legal keywords**.
 * 8. **Final trim** and normalisation.
 *
 * Paragraph structure is preserved by keeping a single blank line between
 * blocks of text.
 *
 * @param text - Raw text extracted from a web page (may contain HTML).
 * @returns Clean, readable text ready for downstream use.
 */
export function cleanText(text: string): string {
  if (!text || typeof text !== 'string') {
    return '';
  }

  let cleaned = text;

  // 1. Replace numeric HTML entities (e.g. &#123;)
  cleaned = cleaned.replace(/&#(\d+);/g, (_match, code: string) => {
    const num = parseInt(code, 10);
    return isNaN(num) ? _match : String.fromCharCode(num);
  });

  // 1b. Replace hex HTML entities (e.g. &#x1F;)
  cleaned = cleaned.replace(/&#x([0-9a-fA-F]+);/g, (_match, hex: string) => {
    const num = parseInt(hex, 16);
    return isNaN(num) ? _match : String.fromCharCode(num);
  });

  // 1c. Replace named HTML entities
  for (const [entity, replacement] of Object.entries(HTML_ENTITIES)) {
    // Case-insensitive replacement for entities
    cleaned = cleaned.split(new RegExp(entity.replace(/&/g, '\\&'), 'gi')).join(replacement);
  }

  // 2. Remove control characters (0x00-0x08, 0x0B-0x0C, 0x0E-0x1F)
  cleaned = cleaned.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]+/g, '');

  // 3. Remove unwanted tags and their content
  cleaned = cleaned.replace(TAG_REMOVE_RE, ' ');

  // 4. Protect paragraph breaks (double newlines) before collapsing
  cleaned = cleaned.replace(/\n{2,}/g, '\u0001');   // temp marker for para break
  cleaned = cleaned.replace(/[\t\n\r\f\v]+/g, ' '); // collapse single whitespace
  cleaned = cleaned.replace(/\s+/g, ' ');
  cleaned = cleaned.replace(/\u0001/g, '\n\n');      // restore paragraph breaks

  // Split into lines for per-line processing
  const rawLines = cleaned.split('\n');
  const processedLines: string[] = [];
  let lastLineWasBlank = false;

  for (const rawLine of rawLines) {
    // 3b. Trim line
    const line = rawLine.trim();

    // 4. Collapse consecutive blank lines to a single blank line
    if (line.length === 0) {
      if (!lastLineWasBlank) {
        processedLines.push('');
        lastLineWasBlank = true;
      }
      continue;
    }
    lastLineWasBlank = false;

    // 5. Remove very short lines (< 3 characters)
    if (line.length < 3) {
      continue;
    }

    // 6. Remove repetitive UI patterns (likely navigation / ads)
    const isRepetitive = REPETITIVE_PATTERNS.some((pattern) =>
      pattern.test(line),
    );
    if (isRepetitive) {
      continue;
    }

    // 7. Remove lines containing ad / legal keywords
    const lowerLine = line.toLowerCase();
    const isAdLine = AD_KEYWORDS.some((keyword) => lowerLine.includes(keyword));
    if (isAdLine) {
      continue;
    }

    processedLines.push(line);
  }

  // Re-join with single newlines (blank lines preserved as empty strings)
  cleaned = processedLines.join('\n');

  // 8. Final trim and whitespace normalisation
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
  cleaned = cleaned.trim();

  return cleaned;
}

/**
 * Strip HTML tags from text using a simple regular-expression fallback.
 *
 * This is an *emergency* utility for when a proper HTML parser is not
 * available. It does **not** decode HTML entities or remove tag content
 * (e.g. `<script>` contents remain).
 *
 * @param html - String that may contain HTML tags.
 * @returns Plain text with all `<…>` sequences removed.
 */
export function stripHtml(html: string): string {
  if (!html || typeof html !== 'string') {
    return '';
  }
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}
