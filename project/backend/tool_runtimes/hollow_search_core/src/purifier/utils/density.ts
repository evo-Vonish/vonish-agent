/**
 * Calculate link density: ratio of link text to total text.
 * High link density is a strong indicator of navigation/sidebar/ad content.
 */
export function calculateLinkDensity(text: string, linkText: string): number {
  if (text.length === 0) return 0;
  return linkText.length / text.length;
}

/**
 * Calculate text density: ratio of text length to number of descendant tags.
 * High text density indicates substantive content (articles, posts).
 */
export function calculateTextDensity(textLength: number, tagCount: number): number {
  if (tagCount === 0) return 0;
  return textLength / tagCount;
}

/**
 * Count CJK (Chinese/Japanese/Korean) characters in text.
 */
export function countCJK(text: string): number {
  return (text.match(/[一-鿿]/g) || []).length;
}

/**
 * Calculate CJK character ratio.
 */
export function cjkRatio(text: string): number {
  if (text.length === 0) return 0;
  return countCJK(text) / text.length;
}

/**
 * Count commas and semicolons (including CJK punctuation U+FF0C, U+FF1B).
 * Comma density is the single strongest predictor of article content (from Readability.js).
 */
export function countCommas(text: string): number {
  return (text.match(/[,，;；]/g) || []).length;
}

/**
 * Check if text appears to be Chinese/Japanese/Korean.
 */
export function isCJK(text: string): boolean {
  return /[一-鿿]/.test(text);
}
