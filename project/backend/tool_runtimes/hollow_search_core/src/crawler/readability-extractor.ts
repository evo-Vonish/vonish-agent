/**
 * Mozilla Readability wrapper for article content extraction.
 *
 * Parses raw HTML through JSDOM and uses Mozilla's Readability library to
 * identify and extract the main article content, producing clean plain text.
 *
 * @module readability-extractor
 */

import { JSDOM } from 'jsdom';
import { Readability } from '@mozilla/readability';

/**
 * Represents the content extracted by Mozilla Readability from a web page.
 */
export interface ExtractedContent {
  /** Article title (from `<title>` or `<h1>` heuristics). */
  title: string;
  /** Full article body as plain text (HTML tags removed). */
  textContent: string;
  /** Short excerpt or summary of the article. */
  excerpt: string;
  /** Author byline, if detected. */
  byline?: string;
  /** Length of `textContent` in characters. */
  length: number;
}

/**
 * Extract article content from HTML using Mozilla Readability.
 *
 * This function parses the provided HTML with JSDOM (supplying the original
 * URL so that relative links resolve correctly), then runs Mozilla's
 * Readability algorithm to identify the main article element and extract
 * clean plain-text content.
 *
 * @param html - Raw HTML string to parse.
 * @param url  - Original page URL (used for resolving relative links and
 *               providing context to Readability).
 * @returns An {@link ExtractedContent} object, or `null` if Readability
 *          cannot identify an article in the page.
 *
 * @example
 * ```ts
 * const result = extractWithReadability(html, 'https://example.com/article');
 * if (result) {
 *   console.log(result.title);       // 'Article Title'
 *   console.log(result.textContent); // 'The article body text...'
 *   console.log(result.excerpt);     // 'A short summary...'
 * }
 * ```
 */
export function extractWithReadability(
  html: string,
  url: string
): ExtractedContent | null {
  if (!html || typeof html !== 'string') {
    return null;
  }

  // Parse the HTML with JSDOM, providing the original URL so that
  // Readability can resolve relative links and apply URL-aware heuristics.
  let dom: JSDOM;
  try {
    dom = new JSDOM(html, { url });
  } catch {
    // JSDOM failed to parse the HTML
    return null;
  }

  // Ensure we have a document with a body to work with
  const document = dom.window.document;
  if (!document || !document.body) {
    return null;
  }

  // Run Readability on the parsed document
  const reader = new Readability(document);
  const parsed = reader.parse();

  // parse() returns null when Readability cannot identify article content
  if (!parsed) {
    return null;
  }

  return {
    title: parsed.title || '',
    textContent: parsed.textContent || '',
    excerpt: parsed.excerpt || '',
    byline: parsed.byline || undefined,
    length: parsed.length || 0,
  };
}
