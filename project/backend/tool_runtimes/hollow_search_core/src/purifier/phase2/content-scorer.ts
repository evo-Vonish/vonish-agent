import type { CheerioAPI } from 'cheerio';
import type { CandidateNode } from '../types.js';
import { countCommas, countCJK, calculateLinkDensity } from '../utils/density.js';
import { getPositiveClassWeight, getNegativeClassWeight } from '../utils/signals.js';
import { detectChineseContent } from './chinese-adaptation.js';

/**
 * Score a content element for Readability candidate selection.
 *
 * Scoring dimensions (from Readability.js + research):
 *   Base: 1 (floor)
 *   Comma/semicolon: +1 per comma (strongest content signal)
 *   Text length: +1 per 100 chars, max 3
 *   CJK chars: +1 per 50 CJK chars, max 5 (Chinese adaptation)
 *   Tag type: DIV+5, PRE/TD/BLOCKQUOTE+3, FORM/OL/UL-3
 *   Class/ID weight: positive patterns +25, negative patterns -25
 *
 * Returns total score.
 */
export function scoreContentElement(
  $el: any,
  $: CheerioAPI,
  useClassWeight: boolean,
): number {
  const text = $el.text().trim();
  if (text.length < 25) return 0;

  let score = 1;

  // Comma bonus — includes CJK comma U+FF0C
  const commaCount = countCommas(text);
  score += commaCount;

  // Length bonus
  score += Math.min(Math.floor(text.length / 100), 3);

  // CJK bonus
  const adaptation = detectChineseContent(text);
  if (adaptation.isChinese) {
    score += Math.min(Math.floor(adaptation.cjkCount / 50), 5);
  }

  // Tag bonus
  const tagName = ($el.prop('tagName') || '').toLowerCase();
  if (tagName === 'div') score += 5;
  if (tagName === 'pre' || tagName === 'td' || tagName === 'blockquote') score += 3;
  if (tagName === 'article') score += 25;
  if (tagName === 'main') score += 20;
  if (tagName === 'section') score += 10;
  if (tagName === 'form') score -= 3;
  if (tagName === 'ol' || tagName === 'ul') score -= 3;

  // Class/ID weight
  if (useClassWeight) {
    const className = ($el.attr('class') || '') + ' ' + ($el.attr('id') || '');
    score += getPositiveClassWeight(className);
    score += getNegativeClassWeight(className);
  }

  return Math.max(0, score);
}

/**
 * Propagate element score to ancestor nodes.
 *
 * Propagation formula (from Readability.js):
 *   L0 (parent):    score / 1
 *   L1 (grandparent): score / 2
 *   L2+:            score / (level * 3)
 *
 * Maximum 5 levels of propagation.
 */
export function propagateScore(
  $el: any,
  $: CheerioAPI,
  elementScore: number,
  candidates: Map<string, CandidateNode>,
  maxLevels: number = 5,
): void {
  let current = $el.parent();
  let level = 0;

  while (current.length && level < maxLevels) {
    const divider = level === 0 ? 1 : level === 1 ? 2 : level * 3;
    const ancestorScore = elementScore / divider;

    const el = current.get(0);
    if (!el) break;

    const key = getElementKey(el, $);

    if (!candidates.has(key)) {
      const text = current.text();
      const linkEls = current.find('a');
      let linkText = '';
      linkEls.each((_i: number, a: any) => { linkText += $(a).text(); });

      candidates.set(key, {
        selector: key,
        score: 0,
        density: calculateLinkDensity(text, linkText),
        textLength: text.length,
        depth: level + 1,
      });
    }

    const candidate = candidates.get(key)!;
    candidate.score += ancestorScore;

    current = current.parent();
    level++;
  }
}

/**
 * Generate a unique key for a DOM element to use in candidate tracking.
 */
function getElementKey(el: any, $: CheerioAPI): string {
  const $el = $(el);
  const tag = el.tagName.toLowerCase();
  const cls = ($el.attr('class') || '').split(/\s+/).slice(0, 3).join('.');
  const id = $el.attr('id') || '';
  const depth = $el.parents().length;
  return `${tag}${id ? '#' + id : ''}${cls ? '.' + cls : ''}@${depth}`;
}
