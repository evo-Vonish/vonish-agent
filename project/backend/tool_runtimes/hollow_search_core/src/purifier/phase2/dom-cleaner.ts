import type { CheerioAPI } from 'cheerio';

/**
 * DOMCleaner — final sanitization pass.
 *
 * Applies a whitelist-based security cleaning:
 *   1. Removes all tags not in ALLOWED_TAGS
 *   2. Strips all attributes not in ALLOWED_ATTRIBUTES (per-tag)
 *   3. Removes event handler attributes (onclick, onload, etc.)
 *   4. Recursively removes empty elements
 *
 * Research ref: sec11.2.7, sec12.1.1
 */

/** Tags permitted in the final clean output — 7 categories */
const ALLOWED_TAGS = new Set([
  // Text content
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'p', 'span', 'div',
  'blockquote', 'pre', 'code',
  'br', 'hr',
  // Inline semantics
  'a', 'strong', 'b', 'em', 'i', 'u', 's', 'del', 'ins',
  'sub', 'sup', 'small', 'mark', 'abbr', 'cite', 'q',
  // Lists
  'ul', 'ol', 'li', 'dl', 'dt', 'dd',
  // Tables
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption',
  // Media
  'img', 'figure', 'figcaption', 'picture', 'source',
  // Semantic
  'article', 'section', 'main', 'header', 'footer', 'nav', 'aside',
  // Embedded
  'iframe', 'video', 'audio',
]);

/** Attributes permitted per tag (only specified tags can have these attributes) */
const ALLOWED_ATTRIBUTES: Record<string, Set<string>> = {
  a: new Set(['href', 'title', 'rel']),
  img: new Set(['src', 'alt', 'width', 'height', 'loading', 'data-src']),
  source: new Set(['src', 'srcset', 'type', 'media']),
  iframe: new Set(['src', 'width', 'height', 'allowfullscreen', 'title']),
  video: new Set(['src', 'width', 'height', 'controls']),
  audio: new Set(['src', 'controls']),
  td: new Set(['colspan', 'rowspan']),
  th: new Set(['colspan', 'rowspan', 'scope']),
  table: new Set([]),
  pre: new Set([]),
  code: new Set([]),
};

/** Event handler attribute prefix */
const EVENT_ATTR_PREFIX = /^on/i;

/**
 * Sanitize the DOM: remove forbidden tags, strip dangerous attributes,
 * remove event handlers, and clean up empty elements.
 *
 * Operates in-place on the Cheerio DOM.
 */
export function sanitize($: CheerioAPI): void {
  // Pass 1: Remove forbidden tags (replace with their text content for inline elements)
  $('*').each((_i: number, el: any) => {
    const tagName = (el.tagName || '').toLowerCase();
    // Skip root/document nodes
    if (!tagName || tagName === 'html' || tagName === 'head' || tagName === 'body') return;

    if (!ALLOWED_TAGS.has(tagName)) {
      const $el = $(el);
      // For block-level forbidden tags, remove with children
      if (['div', 'section', 'nav', 'aside', 'header', 'footer', 'form', 'script', 'style', 'noscript', 'object', 'embed'].includes(tagName)) {
        $el.remove();
      } else {
        // For inline-like tags, replace with their text content
        $el.replaceWith($el.text());
      }
    }
  });

  // Pass 2: Strip forbidden attributes from allowed tags
  $('*').each((_i: number, el: any) => {
    const tagName = (el.tagName || '').toLowerCase();
    const allowed = ALLOWED_ATTRIBUTES[tagName];

    // Get all attributes
    const attrs = Object.keys(el.attribs || {});
    for (const attr of attrs) {
      // Always strip event handlers
      if (EVENT_ATTR_PREFIX.test(attr)) {
        $(el).removeAttr(attr);
        continue;
      }

      // If tag has specific attribute whitelist, strip non-whitelisted attrs
      if (allowed && !allowed.has(attr)) {
        $(el).removeAttr(attr);
        continue;
      }

      // For tags without specific whitelist, keep only standard safe attrs
      if (!allowed) {
        // Allow class, id for generic tags
        if (attr === 'class' || attr === 'id') continue;
        // Strip everything else
        $(el).removeAttr(attr);
      }
    }
  });

  // Pass 3: Recursively remove empty elements (except self-closing tags)
  let emptied: number;
  const selfClosing = new Set(['br', 'hr', 'img', 'source', 'input']);
  do {
    emptied = 0;
    $('*').each((_i: number, el: any) => {
      const tagName = (el.tagName || '').toLowerCase();
      if (selfClosing.has(tagName)) return;
      const $el = $(el);
      // Empty: no text content AND no child elements
      if (!$el.text().trim() && $el.children().length === 0) {
        $el.remove();
        emptied++;
      }
    });
  } while (emptied > 0);
}
