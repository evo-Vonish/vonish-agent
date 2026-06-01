/**
 * Text Cleaner — normalize and clean extracted text.
 */

const HTML_ENTITIES: Record<string, string> = {
  '&nbsp;': ' ',
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&#39;': "'",
  '&ndash;': '-',
  '&mdash;': '-',
  '&hellip;': '...',
  '&copy;': '©',
  '&reg;': '®',
  '&trade;': '™',
};

const AD_KEYWORDS = [
  'advertisement',
  'sponsored',
  'promoted',
  'subscribe now',
  'sign up',
  'click here',
  'learn more',
  'download app',
];

/**
 * Clean extracted text:
 * - Decode HTML entities
 * - Remove ad lines
 * - Normalize whitespace
 * - Preserve paragraph structure
 */
export function cleanText(text: string): string {
  if (!text || text.length === 0) return '';

  let cleaned = text;

  // Decode HTML entities
  for (const [entity, char] of Object.entries(HTML_ENTITIES)) {
    cleaned = cleaned.split(entity).join(char);
  }

  // Remove remaining numeric entities
  cleaned = cleaned.replace(/&#\d+;/g, ' ');

  // Remove control characters
  cleaned = cleaned.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]+/g, '');

  // Remove lines containing ad keywords
  const lines = cleaned.split('\n');
  const filtered = lines.filter((line) => {
    const lower = line.toLowerCase().trim();
    return !AD_KEYWORDS.some((kw) => lower.includes(kw));
  });
  cleaned = filtered.join('\n');

  // Normalize whitespace
  cleaned = cleaned.replace(/[ \t]+/g, ' ');

  // Collapse multiple empty lines
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n');

  return cleaned.trim();
}

/**
 * Strip all HTML tags (emergency fallback).
 */
export function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}
