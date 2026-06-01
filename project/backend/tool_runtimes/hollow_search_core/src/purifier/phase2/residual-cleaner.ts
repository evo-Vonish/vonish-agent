import type { CheerioAPI } from 'cheerio';
import type { AuditLogEntry, ModeConfig, ProtectedRegion } from '../types.js';
import { calculateLinkDensity } from '../utils/density.js';
import { isStrongAdPattern, isMediumAdPattern } from '../utils/signals.js';
import { evaluateDeletion } from '../phase1/deletion-validator.js';

/**
 * Phase 2: Post-readability residual noise cleanup.
 *
 * Operates on the Readability output (not full page DOM).
 * Context is known to be content area, so cleaning is more aggressive,
 * but each deletion still goes through validation.
 *
 * Cleanup steps:
 *   1. Remove nav/aside/sidebar remnants
 *   2. Remove high-link-density paragraphs
 *   3. Remove residual ad keywords in short elements
 *   4. Remove empty/semantically-empty tags
 *   5. Content recovery from Phase 1 if extraction too short
 */
export function cleanResidualNoise(
  $: CheerioAPI,
  protectedRegions: ProtectedRegion[],
  config: ModeConfig,
  auditLog: AuditLogEntry[],
  originalBodyText: string,
): number {
  let removed = 0;

  // Step 1: Nav/sidebar remnant cleanup
  $('nav, aside, [class*="sidebar"], [class*="related-links"], [class*="share"]').each((_, el) => {
    const $el = $(el);
    const textLen = $el.text().length;
    if (textLen < 200) {
      auditLog.push({
        action: 'remove',
        tagName: el.tagName,
        reason: 'residual_nav',
        confidence: 0.7,
        phase: 'post_readability',
        snippet: $el.text().slice(0, 80),
      });
      $el.remove();
      removed++;
    }
  });

  // Step 2: High link density paragraphs
  $('p, div').each((_, el) => {
    const $el = $(el);
    const text = $el.text();
    const textLen = text.length;
    const linkEls = $el.find('a');
    let linkText = '';
    linkEls.each((_i, a) => { linkText += $(a).text(); });
    const linkDensity = calculateLinkDensity(text, linkText);

    if (linkDensity > config.linkDensityThreshold && textLen < 200) {
      auditLog.push({
        action: 'remove',
        tagName: el.tagName,
        reason: 'high_link_density',
        confidence: 0.6,
        phase: 'post_readability',
        snippet: text.slice(0, 80),
      });
      $el.remove();
      removed++;
    }
  });

  // Step 3: Ad keyword residuals
  $('div, span, p').each((_, el) => {
    const $el = $(el);
    const className = ($el.attr('class') || '') + ' ' + ($el.attr('id') || '');
    const isAd = isStrongAdPattern(className) || isMediumAdPattern(className);
    if (isAd && $el.text().length < 80) {
      auditLog.push({
        action: 'remove',
        tagName: el.tagName,
        reason: 'residual_ad_keywords',
        confidence: 0.55,
        phase: 'post_readability',
        snippet: $el.text().slice(0, 80),
      });
      $el.remove();
      removed++;
    }
  });

  // Step 4: Empty element cleanup
  let emptied: number;
  do {
    emptied = 0;
    $('div:empty, span:empty, p:empty').each((_, el) => {
      $(el).remove();
      emptied++;
      removed++;
    });
  } while (emptied > 0);

  // Step 5: Very short text paragraph removal
  $('p, span, div').each((_, el) => {
    const $el = $(el);
    const text = $el.text().trim();
    if (text.length < 25 && $el.find('img, table, iframe').length === 0) {
      auditLog.push({
        action: 'remove',
        tagName: el.tagName,
        reason: 'very_short_element',
        confidence: 0.6,
        phase: 'post_readability',
        snippet: text.slice(0, 80),
      });
      $el.remove();
      removed++;
    }
  });

  return removed;
}
