import type { ProtectionSignal } from '../types.js';
import { cjkRatio, calculateLinkDensity, calculateTextDensity, countCommas } from './density.js';

/**
 * Strong ad patterns — high confidence ad indicators.
 * Matched against combined class + id strings.
 */
const STRONG_AD_PATTERNS = [
  /\badsbygoogle\b/i,
  /\bgoogle[_\-]?ads\b/i,
  /\badsense\b/i,
  /\bad[_\-]?banner\b/i,
  /\bad[_\-]?container\b/i,
  /\bad[_\-]?wrapper\b/i,
  /\bad[_\-]?slot\b/i,
  /\bdoubleclick\b/i,
  /\badvertisement\b/i,
  /\bsponsor(ed|ship)?\b/i,
];

/**
 * Medium ad patterns — moderate confidence.
 */
const MEDIUM_AD_PATTERNS = [
  /\bcookie[_\-]?(banner|consent|notice|policy)\b/i,
  /\bsubscribe\b/i,
  /\bnewsletter\b/i,
  /\bpopup\b/i,
  /\bmodal[_\-]?(overlay)?\b/i,
  /\bsocial[_\-]?share\b/i,
  /\bshare[_\-]?(button|bar)\b/i,
  /\brelated[_\-]?posts\b/i,
  /\brecommend(ed|ations)\b/i,
  /\byou[_\-]?may[_\-]?like\b/i,
  /\bcomment(s)?\b/i,
  /\bdisqus\b/i,
  /\btracking\b/i,
  /\banalytics\b/i,
  /\bnav(igation|bar)?\b/i,
  /\bsidebar\b/i,
];

/**
 * Positive content class patterns — strong indicators of article body.
 */
const POSITIVE_CONTENT_PATTERNS = [
  /\barticle[_\-]?(body|content|text)?\b/i,
  /\bpost[_\-]?(content|body|text|article)?\b/i,
  /\bentry[_\-]?(content|body)?\b/i,
  /\bstory[_\-]?(body|content)?\b/i,
  /\bnews[_\-]?(content|article)?\b/i,
  /\bmain[_\-]?(text|content)?\b/i,
  /\bcontent[_\-]?(body|area|main|wrapper)?\b/i,
  /\btext[_\-]?body\b/i,
];

/**
 * Negative content class patterns — indicators of non-content.
 */
const NEGATIVE_CONTENT_PATTERNS = [
  /\bcomment(s)?\b/i,
  /\bmeta\b/i,
  /\bfooter\b/i,
  /\bsidebar\b/i,
  /\bwidget\b/i,
  /\bshare\b/i,
  /\bcommercial\b/i,
  /\bad[_\-]?break\b/i,
  /\bpromo\b/i,
  /\baffiliate\b/i,
];

export function isStrongAdPattern(className: string): boolean {
  return STRONG_AD_PATTERNS.some(p => p.test(className));
}

export function isMediumAdPattern(className: string): boolean {
  return MEDIUM_AD_PATTERNS.some(p => p.test(className));
}

export function getPositiveClassWeight(className: string): number {
  let weight = 0;
  if (POSITIVE_CONTENT_PATTERNS.some(p => p.test(className))) weight += 25;
  // Extra weight for highly specific patterns
  if (/\b(article-body|post-content|entry-content|story-body|news-content)\b/i.test(className)) weight += 30;
  return weight;
}

export function getNegativeClassWeight(className: string): number {
  let weight = 0;
  if (NEGATIVE_CONTENT_PATTERNS.some(p => p.test(className))) weight -= 20;
  if (/\b(commercial|ad-break|promo|sponsored|affiliate)\b/i.test(className)) weight -= 25;
  return weight;
}

/**
 * Detect if an element text signals a protected content region.
 * Returns list of protection signals found.
 */
export function detectContentSignals(
  tagName: string,
  className: string,
  text: string,
  linkText: string,
  tagCount: number,
): ProtectionSignal[] {
  const signals: ProtectionSignal[] = [];

  // Signal 1: Semantic tags
  const semanticTags = ['article', 'main'];
  if (semanticTags.includes(tagName.toLowerCase())) {
    signals.push({ type: 'semantic_tag', confidence: 0.95, weight: 1.0, selector: tagName });
  }

  // Signal 2: Class/id name signals
  const combined = className;
  if (POSITIVE_CONTENT_PATTERNS.some(p => p.test(combined))) {
    signals.push({ type: 'class_signal', confidence: 0.9, weight: 0.9, selector: className });
  }

  // Signal 3: Text density signal
  const textLen = text.length;
  const textDensity = calculateTextDensity(textLen, tagCount);
  const linkDensity = calculateLinkDensity(text, linkText);
  if (textDensity > 10 && linkDensity < 0.2 && textLen > 200) {
    signals.push({
      type: 'text_density',
      confidence: Math.min(0.95, 0.7 + textDensity / 100),
      weight: 0.85,
      selector: `textDensity=${textDensity.toFixed(1)}`,
    });
  }

  // Signal 4: CJK density signal
  const cjk = cjkRatio(text);
  if (cjk > 0.3 && textLen > 100) {
    signals.push({
      type: 'cjk_density',
      confidence: 0.8 + cjk * 0.15,
      weight: 0.75,
      selector: `cjkRatio=${(cjk * 100).toFixed(1)}%`,
    });
  }

  // Signal 5: Link density signal (low = content)
  if (linkDensity < 0.1 && textLen > 200) {
    signals.push({
      type: 'link_density',
      confidence: 0.7,
      weight: 0.7,
      selector: `linkDensity=${linkDensity.toFixed(2)}`,
    });
  }

  // Signal 6: Comma count (high comma density = article text)
  const commas = countCommas(text);
  if (commas >= 3 && textLen > 100) {
    signals.push({
      type: 'text_density',
      confidence: 0.65 + Math.min(commas / 50, 0.25),
      weight: 0.65,
      selector: `commas=${commas}`,
    });
  }

  return signals;
}

export { STRONG_AD_PATTERNS, MEDIUM_AD_PATTERNS, POSITIVE_CONTENT_PATTERNS, NEGATIVE_CONTENT_PATTERNS };
