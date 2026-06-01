/**
 * Text extraction coordinator for the crawler module.
 *
 * Orchestrates HTML-to-text conversion by first attempting Mozilla Readability
 * for high-quality article extraction, then falling back to a basic DOM
 * textContent strategy when Readability cannot identify article content.
 *
 * @module extract-text
 */

import { JSDOM } from 'jsdom';
import { extractWithReadability, ExtractedContent } from './readability-extractor.js';
import { cleanText } from './clean-text.js';

/**
 * Options for text extraction.
 */
export interface ExtractOptions {
  /** Raw HTML string to extract text from. */
  html: string;
  /** Original page URL (passed to Readability for link resolution). */
  url: string;
  /** Maximum number of characters to retain (truncates with "..."). */
  maxTextChars?: number;
}

/**
 * Structured result of a text extraction operation.
 */
export interface ExtractedText {
  /** Article or page title. */
  title: string;
  /** Clean, plain-text body content. */
  text: string;
  /** Short excerpt or summary. */
  excerpt: string;
  /** Approximate word count (space-delimited tokens). */
  wordCount: number;
  /** Total character count (including whitespace). */
  charCount: number;
}

/** Ellipsis marker appended when text is truncated. */
const TRUNCATION_MARKER = '...';

/**
 * Extract and clean text from HTML.
 *
 * Strategy:
 * 1. **Readability first** – Uses Mozilla Readability to identify and extract
 *    the main article content with high-quality plain text.
 * 2. **Fallback to basic extraction** – If Readability cannot identify article
 *    content (returns `null`), falls back to extracting the full `textContent`
 *    of the `<body>` element via JSDOM.
 * 3. **Text cleaning** – The extracted text is run through {@link cleanText}
 *    to normalise whitespace, collapse blank lines, and remove invisible
 *    control characters.
 * 4. **Truncation** – If `maxTextChars` is specified and the cleaned text
 *    exceeds that length, it is truncated with an ellipsis.
 *
 * @param options - Extraction configuration including HTML, URL, and optional
 *                  character limit.
 * @returns An {@link ExtractedText} structure, or `null` if no extractable
 *          text could be found.
 *
 * @example
 * ```ts
 * const result = extractText({
 *   html: '<html><body><article><p>Hello world</p></article></body></html>',
 *   url: 'https://example.com',
 *   maxTextChars: 5000,
 * });
 * if (result) {
 *   console.log(result.title);     // '' or detected title
 *   console.log(result.text);      // 'Hello world'
 *   console.log(result.wordCount); // 2
 * }
 * ```
 */
export function extractText(options: ExtractOptions): ExtractedText | null {
  const { html, url, maxTextChars } = options;

  if (!html || typeof html !== 'string') {
    return null;
  }

  // ------------------------------------------------------------------
  // Step 1: Try Mozilla Readability for high-quality article extraction
  // ------------------------------------------------------------------
  let extracted: ExtractedContent | null = null;
  try {
    extracted = extractWithReadability(html, url);
  } catch {
    // Readability threw an error — proceed to fallback
    extracted = null;
  }

  // ------------------------------------------------------------------
  // Step 2: Fallback to basic body textContent extraction
  // ------------------------------------------------------------------
  let rawTitle = '';
  let rawText = '';
  let rawExcerpt = '';

  if (extracted && extracted.textContent && extracted.textContent.trim().length > 0) {
    // Readability succeeded
    rawTitle = extracted.title || '';
    rawText = extracted.textContent;
    rawExcerpt = extracted.excerpt || '';
  } else {
    // Fallback: extract all text from the body element
    const fallbackResult = extractFallback(html, url);
    if (!fallbackResult) {
      return null;
    }
    rawTitle = fallbackResult.title;
    rawText = fallbackResult.text;
    rawExcerpt = fallbackResult.excerpt;
  }

  // ------------------------------------------------------------------
  // Step 3: Clean the extracted text
  // ------------------------------------------------------------------
  const cleanedTitle = cleanText(rawTitle);
  const cleanedText = cleanText(rawText);
  const cleanedExcerpt = rawExcerpt ? cleanText(rawExcerpt) : '';

  if (!cleanedText || cleanedText.length === 0) {
    return null;
  }

  // ------------------------------------------------------------------
  // Step 4: Apply maxTextChars truncation if specified
  // ------------------------------------------------------------------
  let finalText = cleanedText;
  let truncated = false;

  if (maxTextChars && maxTextChars > 0 && cleanedText.length > maxTextChars) {
    // Reserve space for the truncation marker
    const reserve = TRUNCATION_MARKER.length;
    const cutAt = Math.max(1, maxTextChars - reserve);
    finalText = cleanedText.slice(0, cutAt) + TRUNCATION_MARKER;
    truncated = true;
  }

  // Build excerpt: prefer Readability excerpt, otherwise derive from text
  let excerpt = cleanedExcerpt;
  if (!excerpt || excerpt.length === 0) {
    // Derive excerpt from the first ~200 characters of the text
    excerpt = finalText.slice(0, 200).trim();
    if (finalText.length > 200) {
      excerpt += TRUNCATION_MARKER;
    }
  } else if (truncated && excerpt.length > maxTextChars!) {
    // Also truncate excerpt if it exceeds the limit
    const reserve = TRUNCATION_MARKER.length;
    const cutAt = Math.max(1, (maxTextChars ?? excerpt.length) - reserve);
    excerpt = excerpt.slice(0, cutAt) + TRUNCATION_MARKER;
  }

  // ------------------------------------------------------------------
  // Step 5: Compute statistics and return
  // ------------------------------------------------------------------
  const charCount = finalText.length;
  const wordCount = finalText.split(/\s+/).filter((w) => w.length > 0).length;

  return {
    title: cleanedTitle,
    text: finalText,
    excerpt,
    wordCount,
    charCount,
  };
}

// ---------------------------------------------------------------------------
// Fallback extraction helper
// ---------------------------------------------------------------------------

/**
 * Fallback text extraction using basic JSDOM textContent.
 *
 * When Readability fails to identify article content, this function extracts
 * the text content of the `<body>` element and attempts to derive a title
 * from `<title>` or `<h1>` tags.
 *
 * @param html - Raw HTML string.
 * @param url  - Page URL for JSDOM context.
 * @returns A simple title/text/excerpt tuple, or `null` if extraction fails.
 *
 * @internal
 */
function extractFallback(
  html: string,
  url: string
): { title: string; text: string; excerpt: string } | null {
  let dom: JSDOM;
  try {
    dom = new JSDOM(html, { url });
  } catch {
    return null;
  }

  const document = dom.window.document;
  if (!document || !document.body) {
    return null;
  }

  // Extract body text
  const bodyText = document.body.textContent || '';
  if (!bodyText.trim()) {
    return null;
  }

  // Try to find a title
  const titleTag = document.querySelector('title');
  const h1Tag = document.querySelector('h1');
  const title = titleTag?.textContent || h1Tag?.textContent || '';

  // Derive excerpt from the first portion of body text
  const cleanedBody = cleanText(bodyText);
  const excerpt = cleanedBody.length > 200
    ? cleanedBody.slice(0, 200) + '...'
    : cleanedBody;

  return { title: title.trim(), text: bodyText, excerpt };
}
