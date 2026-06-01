/**
 * Calculate overall quality score for purified content.
 *
 * Quality dimensions (each 0-1, weighted):
 *   - Content length adequacy
 *   - Structure richness (paragraphs, headings)
 *   - Noise reduction ratio
 *   - Text density
 */
export function calculateQualityScore(params: {
  cleanText: string;
  cleanHtml: string;
  originalTextLength: number;
  removedCount: number;
  protectedCount: number;
}): number {
  const { cleanText, cleanHtml, originalTextLength, removedCount, protectedCount } = params;
  let score = 0.5;

  // Content length (higher is better, up to a point)
  const textLen = cleanText.length;
  if (textLen > 3000) score += 0.15;
  else if (textLen > 1000) score += 0.1;
  else if (textLen > 500) score += 0.05;
  else if (textLen < 100) score -= 0.3;
  else if (textLen < 200) score -= 0.15;

  // Structure richness
  const pCount = (cleanHtml.match(/<p[\s>]/gi) || []).length;
  if (pCount >= 5) score += 0.1;
  else if (pCount >= 2) score += 0.05;

  const hCount = (cleanHtml.match(/<h[1-6][\s>]/gi) || []).length;
  if (hCount >= 3) score += 0.1;
  else if (hCount >= 1) score += 0.05;

  // Noise reduction (good ratio = high quality filtering)
  if (originalTextLength > 0) {
    const reductionRatio = textLen / originalTextLength;
    // If we kept 30-70% of original text, filtering was effective
    if (reductionRatio > 0.3 && reductionRatio < 0.9) score += 0.1;
    // If we kept <10% or >95%, something might be wrong
    if (reductionRatio < 0.1) score -= 0.1;
  }

  // Protection effectiveness
  if (protectedCount > 0 && removedCount > 0) score += 0.05;

  // Cleanup effectiveness
  if (removedCount > 0) score += 0.05;

  return Math.max(0, Math.min(1, Math.round(score * 100) / 100));
}
