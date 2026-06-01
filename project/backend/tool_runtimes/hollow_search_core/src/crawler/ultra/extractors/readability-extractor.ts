/**
 * Mozilla Readability wrapper — high-quality article extraction.
 * Used for 'deep' preset and as fallback in 'hybrid' mode.
 */

import { JSDOM } from 'jsdom';
import { Readability } from '@mozilla/readability';

export interface ReadabilityExtractResult {
  title: string;
  textContent: string;
  excerpt: string;
  byline?: string;
  length: number;
}

/**
 * Extract article content using Mozilla Readability.
 * Falls back to null if the page is not an article.
 */
export function extractWithReadability(
  html: string,
  url: string,
): ReadabilityExtractResult | null {
  // Truncate very large HTML to avoid JSDOM memory issues
  const MAX_HTML_SIZE = 300 * 1024;
  const truncatedHtml =
    html.length > MAX_HTML_SIZE ? html.slice(0, MAX_HTML_SIZE) + '</body></html>' : html;

  const dom = new JSDOM(truncatedHtml, { url });
  const reader = new Readability(dom.window.document);
  const article = reader.parse();

  if (!article) return null;

  return {
    title: article.title || '',
    textContent: article.textContent || '',
    excerpt: article.excerpt || article.textContent?.slice(0, 200) || '',
    byline: article.byline || undefined,
    length: article.length ?? article.textContent?.length ?? 0,
  };
}
