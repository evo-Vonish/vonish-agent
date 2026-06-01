import { countCJK, cjkRatio } from '../utils/density.js';

/**
 * Chinese/Japanese/Korean content adaptation.
 *
 * Key adjustments for CJK content (from research sec10.5):
 * - Character threshold: 500 → 250 (CJK encodes more information per character)
 * - CJK comma (U+FF0C) included in comma scoring
 * - CJK character ratio used as independent scoring signal
 * - Lower text length thresholds throughout
 */

export interface ChineseAdaptation {
  isChinese: boolean;
  charThreshold: number;
  cjkCount: number;
  cjkRatio: number;
}

/**
 * Detect if content is primarily CJK and compute adapted thresholds.
 */
export function detectChineseContent(text: string): ChineseAdaptation {
  const cjkCount = countCJK(text);
  const ratio = cjkRatio(text);
  const isChinese = ratio > 0.15;

  return {
    isChinese,
    charThreshold: isChinese ? 250 : 500,
    cjkCount,
    cjkRatio: ratio,
  };
}

/**
 * Adapt char threshold for mixed content.
 * CJK text encodes roughly 2x the information per character vs English.
 */
export function getAdaptiveCharThreshold(text: string, baseThreshold: number): number {
  const ratio = cjkRatio(text);
  if (ratio > 0.3) return Math.min(baseThreshold, 250);
  if (ratio > 0.15) return Math.min(baseThreshold, 350);
  return baseThreshold;
}

/**
 * Calculate CJK scoring bonus for Readability scoreElement.
 * +1 per 50 CJK characters, max +5.
 */
export function calculateCJKScore(text: string): number {
  const cjkCount = countCJK(text);
  return Math.min(Math.floor(cjkCount / 50), 5);
}

/**
 * Check if text meets the minimum content threshold for CJK content.
 */
export function meetsCJKThreshold(text: string, threshold?: number): boolean {
  const effectiveThreshold = threshold || getAdaptiveCharThreshold(text, 500);
  return text.length >= effectiveThreshold;
}
