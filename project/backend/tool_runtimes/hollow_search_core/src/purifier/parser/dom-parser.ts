import * as cheerio from 'cheerio';
import type { CheerioAPI } from 'cheerio';

/**
 * Parse HTML string into a Cheerio DOM.
 *
 * Cheerio is used for Phase 1 and Phase 2 DOM manipulation
 * because it's faster than JSDOM for select-and-remove operations.
 * JSDOM is only used for Mozilla Readability (which needs a full DOM).
 */
export function parseDOM(html: string): CheerioAPI {
  return cheerio.load(html, {
    xml: {
      decodeEntities: true,
      xmlMode: false,
    },
  });
}

/**
 * Get the inner HTML of a Cheerio selection.
 */
export function getInnerHTML($: CheerioAPI, selector?: string): string {
  if (selector) {
    return $(selector).html() || '';
  }
  return $.html();
}

/**
 * Get the text content of a Cheerio selection.
 */
export function getText($: CheerioAPI, selector?: string): string {
  if (selector) {
    return $(selector).text().trim();
  }
  return $('body').text().trim();
}
