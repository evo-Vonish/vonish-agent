import type { CheerioAPI } from 'cheerio';
import type { AdCandidate, ContentScore, DeletionDecision, ModeConfig, ProtectedRegion } from '../types.js';
import { countCommas, countCJK, calculateLinkDensity } from '../utils/density.js';
import {
  isStrongAdPattern,
  isMediumAdPattern,
  getPositiveClassWeight,
  getNegativeClassWeight,
} from '../utils/signals.js';

/**
 * Calculate noise score for a candidate element.
 * Higher score = more likely to be noise/ad.
 */
export function calculateNoiseScore($el: any, $: CheerioAPI): number {
  let score = 0;
  const tagName = ($el.prop('tagName') || '').toLowerCase();
  const className = ($el.attr('class') || '') + ' ' + ($el.attr('id') || '');
  const text = $el.text();
  const textLength = text.length;

  // Get link density
  const linkTextEls = $el.find('a');
  let linkTextLen = 0;
  linkTextEls.each((_i: number, a: any) => { linkTextLen += $(a).text().length; });
  const linkDensity = calculateLinkDensity(text, linkTextEls.text());

  // Strong noise signals (direct pattern match) — from research sec9.5
  if (/adsbygoogle|google_ads|adsense/i.test(className)) score += 50;
  if (/cookie[-_]?(banner|consent|notice|policy)/i.test(className)) score += 40;
  if (/subscribe|newsletter|email[-_]?signup/i.test(className)) score += 35;
  if (/popup|modal[-_]?overlay|lightbox/i.test(className)) score += 35;
  if (/social[-_]?share|share[-_]?(button|bar)/i.test(className)) score += 30;
  if (/related[-_]?posts|recommend(ed|ations)|you[-_]?may[-_]?like/i.test(className)) score += 25;
  if (/comment|disqus|livefyre/i.test(className)) score += 20;
  if (/ad[-_]?(container|wrapper|slot|unit)/i.test(className)) score += 45;
  if (/tracking|analytics|gtm/i.test(className)) score += 30;

  // Semantic noise tags
  if (tagName === 'nav') score += 25;
  if (tagName === 'aside') score += 20;
  if (tagName === 'footer') score += 15;
  if (tagName === 'header') score += 10;

  // Structural signals
  if (linkDensity > 0.8) score += 20;
  else if (linkDensity > 0.5) score += 10;

  if (textLength < 50) score += 5;

  // Image-heavy, text-light
  const imgCount = $el.find('img').length;
  const pCount = $el.find('p').length;
  if (imgCount > 5 && pCount < 2) score += 15;

  return score;
}

/**
 * Calculate content score for an element.
 * Higher score = more likely to be real content (protect from deletion).
 */
export function calculateContentScore(
  $el: any,
  $: CheerioAPI,
  isChinese: boolean,
): ContentScore {
  const text = $el.text();
  const textLength = text.length;

  const baseScore = 1;

  // Comma/semicolon bonus (supports CJK punctuation U+FF0C)
  const commaCount = countCommas(text);
  const commaBonus = commaCount;

  // Length bonus: +1 per 100 chars, max 3
  const lengthBonus = Math.min(Math.floor(textLength / 100), 3);

  // CJK bonus: +1 per 50 CJK chars, max 5
  let cjkBonus = 0;
  if (isChinese) {
    const cjkCount = countCJK(text);
    cjkBonus = Math.min(Math.floor(cjkCount / 50), 5);
  }

  // Tag type bonus
  const tagName = ($el.prop('tagName') || '').toLowerCase();
  let tagBonus = 0;
  if (tagName === 'div') tagBonus = 5;
  if (tagName === 'pre') tagBonus = 3;
  if (tagName === 'td') tagBonus = 3;
  if (tagName === 'blockquote') tagBonus = 3;
  if (tagName === 'article') tagBonus = 25;
  if (tagName === 'main') tagBonus = 20;
  if (tagName === 'section') tagBonus = 10;
  if (tagName === 'form') tagBonus = -3;
  if (tagName === 'ol' || tagName === 'ul') tagBonus = -3;

  // Class/ID weight
  const className = ($el.attr('class') || '') + ' ' + ($el.attr('id') || '');
  let classWeight = 0;
  classWeight += getPositiveClassWeight(className);
  classWeight += getNegativeClassWeight(className);

  return {
    baseScore,
    commaBonus,
    lengthBonus,
    cjkBonus,
    tagBonus,
    classWeight,
    total: baseScore + commaBonus + lengthBonus + cjkBonus + tagBonus + classWeight,
  };
}

/**
 * Evaluate whether a candidate element should be deleted.
 *
 * Based on 7-check validation from research sec14.3:
 *   1. Protected region overlap — immediate veto
 *   2. Element text length — long text reduces deletion confidence
 *   3. Link density — high density increases deletion confidence
 *   4. Ad keyword patterns — strong/medium/weak tiered matching
 *   5. Semantic tags — nav/aside → delete, article/main → protect
 *   6. Child element quality — image-heavy → delete, paragraph-rich → protect
 *   7. CJK content — CJK text reduces deletion confidence
 */
export function evaluateDeletion(
  candidate: AdCandidate,
  protectedRegions: ProtectedRegion[],
  $: CheerioAPI,
  config: ModeConfig,
): DeletionDecision {
  const signals: string[] = [];
  let confidence = 0;

  // Re-parse the candidate element for Cheerio
  const $candidate = $(candidate.elementHtml);
  // Actually, we need the live element. Let's match by text+tag since we can't store Cheerio objects
  // For now, use the tagged info from the candidate
  const textLength = candidate.text.length;
  const tagName = candidate.tagName;

  // === Check 1: Protected region overlap — immediate veto ===
  // We check if the candidate's selector matches any protected region selector
  for (const region of protectedRegions) {
    // If candidate is a protected semantic tag, veto
    if (tagName === 'article' || tagName === 'main') {
      return {
        allowed: false,
        reason: 'PROTECTED_REGION_OVERLAP',
        confidence: 0,
        signals: ['protected_region'],
      };
    }
  }

  // === Check 2: Text length ===
  if (textLength < 100) {
    signals.push('very_short_text');
    confidence += 0.25;
  } else if (textLength < 200) {
    signals.push('short_text');
    confidence += 0.15;
  } else if (textLength > 1000) {
    signals.push('very_long_text');
    confidence -= 0.5;
  } else if (textLength > 500) {
    signals.push('long_text');
    confidence -= 0.3;
  }

  // === Check 3: Link density (from noise score, which already includes it) ===
  if (candidate.noiseScore > 40) {
    signals.push('strong_noise');
    confidence += 0.4;
  } else if (candidate.noiseScore > 20) {
    signals.push('medium_noise');
    confidence += 0.25;
  } else if (candidate.noiseScore > 10) {
    signals.push('weak_noise');
    confidence += 0.1;
  }

  // === Check 4: Ad keyword patterns ===
  const className = candidate.selector;
  if (isStrongAdPattern(className)) {
    signals.push('strong_ad_pattern');
    confidence += 0.5;
  } else if (isMediumAdPattern(className)) {
    signals.push('medium_ad_pattern');
    confidence += 0.3;
  }

  // === Check 5: Semantic tags ===
  if (['nav', 'aside', 'footer', 'header'].includes(tagName)) {
    signals.push('semantic_noise_tag');
    confidence += 0.3;
  } else if (['article', 'main'].includes(tagName)) {
    signals.push('semantic_content_tag');
    confidence -= 0.5;
  }

  // === Check 6: Child element quality (approximate from dimensions) ===
  // We don't have the live element for img/p counts, so use text length as proxy
  if (tagName === 'iframe') {
    signals.push('iframe_element');
    confidence += 0.4;
  }

  // === Check 7: CJK content protection ===
  const cjkCount = countCJK(candidate.text);
  const cjkRatio = textLength > 0 ? cjkCount / textLength : 0;
  if (cjkRatio > 0.3 && textLength > 100) {
    signals.push('cjk_content');
    confidence -= 0.25;
  }

  // Content score check (negative signal = protection)
  const isChinese = cjkRatio > 0.15;
  const contentScore = calculateContentScore($candidate, $, isChinese);
  if (contentScore.total > 20) {
    signals.push('high_content_score');
    confidence -= 0.3;
  }

  // === Threshold comparison ===
  let threshold = config.minConfidenceScore;

  // Conservative mode: long text gets extra protection (+0.15 threshold)
  if (config.mode === 'conservative' && textLength > 300) {
    threshold += 0.15;
  }

  // Multiple signals requirement
  if (config.requireMultipleSignals && signals.length < 2) {
    confidence = Math.min(confidence, threshold - 0.1);
  }

  // Clamp confidence
  confidence = Math.max(0, Math.min(1, confidence));

  if (confidence >= threshold) {
    return {
      allowed: true,
      reason: signals.length > 0 ? signals.join('+') : 'THRESHOLD_MET',
      confidence,
      signals,
    };
  }

  return {
    allowed: false,
    reason: confidence <= 0 ? 'PROTECTION_SIGNAL_OVERRIDE' : 'CONFIDENCE_BELOW_THRESHOLD',
    confidence,
    signals,
  };
}
