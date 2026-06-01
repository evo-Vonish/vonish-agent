/**
 * Noise Filter — detect and filter low-quality / non-content text.
 */

const NOISE_PATTERNS = [
  // Login / subscription walls
  /please\s+log\s*in|sign\s*in\s*to\s*continue|subscription\s*required/i,
  // Empty placeholder
  /this\s*page\s*is\s*intentionally\s*left\s*blank|content\s*coming\s*soon/i,
  // Copyright only
  /^\s*©\s*\d{4}\s*[^.]{0,50}\.?\s*$/,
  // Too short
  /^.{0,50}$/,
  // Navigation-like
  /home\s*\|\s*about\s*\|\s*contact\s*\||site\s*map|breadcrumb/i,
];

/**
 * Check if text is noise (not real content).
 */
export function isNoise(text: string): boolean {
  return NOISE_PATTERNS.some((p) => p.test(text));
}

/**
 * Calculate content ratio (actual content vs total text).
 */
export function contentRatio(text: string): number {
  const totalLen = text.length;
  if (totalLen === 0) return 0;

  // Remove common noise patterns
  let content = text;
  content = content.replace(/[\n\r\t]+/g, ' ');
  content = content.replace(/\s{2,}/g, ' ');

  // Count meaningful characters (CJK + Latin words + numbers)
  const meaningfulChars = (content.match(/[\w\u4e00-\u9fff]/g) || []).length;
  return meaningfulChars / totalLen;
}

/**
 * Filter results that are mostly noise.
 */
export function filterNoiseResults<T extends { text: string }>(
  results: T[],
  minRatio: number = 0.3,
): T[] {
  return results.filter((r) => {
    if (isNoise(r.text)) return false;
    return contentRatio(r.text) >= minRatio;
  });
}
