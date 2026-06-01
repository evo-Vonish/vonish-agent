/**
 * Fast Text Extractor — lightweight cheerio-based extraction.
 * No JSDOM overhead. Used for 'fast' and 'maximum' / 'unlimited' presets
 * where speed matters more than accuracy.
 */

import * as cheerio from 'cheerio';

export interface FastExtractResult {
  title: string;
  text: string;
  excerpt: string;
}

/**
 * Extract text using cheerio (no JSDOM — much faster).
 * Strategy: find the largest text block and extract it.
 */
export function extractTextFast(html: string, url: string): FastExtractResult {
  const $ = cheerio.load(html);

  // Remove script/style/nav/footer/header/iframe
  $('script, style, nav, footer, header, iframe, aside, .sidebar, .advertisement, .ad, noscript').remove();

  // Extract title
  let title = $('title').text().trim() || $('h1').first().text().trim() || '';

  // Strategy: find the element with the most paragraph text
  const candidates: Array<{ text: string; wordCount: number }> = [];

  // Candidate 1: article tag
  $('article').each((_idx: number, el: any) => {
    const text = $(el).text().trim();
    if (text.length > 50) {
      candidates.push({ text, wordCount: text.split(/\s+/).length });
    }
  });

  // Candidate 2: main tag
  $('main').each((_idx: number, el: any) => {
    const text = $(el).text().trim();
    if (text.length > 50) {
      candidates.push({ text, wordCount: text.split(/\s+/).length });
    }
  });

  // Candidate 3: div with lots of paragraphs
  $('div').each((_idx: number, el: any) => {
    const paraCount = $(el).find('p').length;
    if (paraCount >= 2) {
      const text = $(el).text().trim();
      if (text.length > 50) {
        candidates.push({ text, wordCount: text.split(/\s+/).length });
      }
    }
  });

  // Candidate 4: body as fallback (always include)
  const bodyText = $('body').text().trim();
  if (bodyText.length > 20) {
    candidates.push({ text: bodyText, wordCount: bodyText.split(/\s+/).length });
  }

  // Pick the candidate with the most words (likely the main content)
  let bestText = '';
  let bestWords = 0;
  for (const c of candidates) {
    if (c.wordCount > bestWords) {
      bestWords = c.wordCount;
      bestText = c.text;
    }
  }

  // Clean up the text
  const text = bestText
    .replace(/\s+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  return {
    title,
    text,
    excerpt: text.slice(0, 200),
  };
}
