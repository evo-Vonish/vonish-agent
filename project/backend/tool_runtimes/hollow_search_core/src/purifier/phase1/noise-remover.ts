import type { CheerioAPI } from 'cheerio';
import type { AuditLogEntry, ModeConfig, ProtectedRegion } from '../types.js';
import { collectAdCandidates } from './cosmetic-filter.js';
import { detectProtectedRegions } from './content-protector.js';
import { evaluateDeletion } from './deletion-validator.js';
import { describeElement } from '../utils/element-desc.js';

/**
 * Phase 1: DOM pre-processing and ad noise removal.
 *
 * Flow:
 *   1. Detect protected content regions (6-signal fusion)
 *   2. Collect ad candidates (safe selectors + heuristics)
 *   3. Evaluate deletion with multi-signal confirmation
 *   4. Execute deletions + record audit log
 *   5. Remove untrusted tags (script, style, iframe, etc.)
 *
 * Returns cleaned HTML, audit log, and metadata.
 */
export function runPhase1(
  $: CheerioAPI,
  url: string,
  config: ModeConfig,
): {
  html: string;
  protectedRegions: ProtectedRegion[];
  removedCount: number;
  auditLog: AuditLogEntry[];
} {
  const auditLog: AuditLogEntry[] = [];
  let removedCount = 0;

  // Extract hostname from URL
  let hostname: string | undefined;
  try {
    hostname = new URL(url).hostname;
  } catch {
    hostname = undefined;
  }

  // Step 1: Detect protected regions
  const protectedRegions = detectProtectedRegions($, config);

  // Step 2: Collect ad candidates
  const candidates = collectAdCandidates($, config, hostname);

  // Step 3 & 4: Evaluate and execute
  for (const candidate of candidates) {
    const decision = evaluateDeletion(candidate, protectedRegions, $, config);

    if (decision.allowed) {
      // Find and remove the matching element
      // Use a try-catch to handle selectors that might fail
      try {
        const $els = $(candidate.selector);
        $els.each((_i, el) => {
          const $el = $(el);
          // Double-check: is this element text similar to our candidate?
          if ($el.text().slice(0, 80) === candidate.text.slice(0, 80)) {
            auditLog.push({
              action: 'remove',
              tagName: candidate.tagName,
              selector: candidate.selector,
              reason: decision.reason,
              confidence: decision.confidence,
              phase: 'pre_readability',
              snippet: candidate.text.slice(0, 100),
              signals: decision.signals,
            });
            $el.remove();
            removedCount++;
          }
        });
      } catch {
        // Selector failed, skip
        auditLog.push({
          action: 'skip',
          tagName: candidate.tagName,
          selector: candidate.selector,
          reason: 'SELECTOR_ERROR',
          confidence: 0,
          phase: 'pre_readability',
        });
      }
    } else {
      auditLog.push({
        action: 'protect',
        tagName: candidate.tagName,
        reason: decision.reason,
        confidence: decision.confidence,
        phase: 'pre_readability',
        signals: decision.signals,
      });
    }
  }

  // Step 5: Remove untrusted tags
  const forbiddenTags = ['script', 'style', 'noscript', 'embed', 'object'];
  for (const tag of forbiddenTags) {
    $(tag).each((_i, el) => {
      const $el = $(el);
      auditLog.push({
        action: 'remove',
        tagName: tag,
        reason: 'UNTRUSTED_TAG',
        confidence: 1.0,
        phase: 'pre_readability',
        snippet: $el.text().slice(0, 80),
      });
      $el.remove();
      removedCount++;
    });
  }

  // Remove iframes (often ads/tracking) but not if keepVideos would apply
  $('iframe').each((_i, el) => {
    const $el = $(el);
    const src = $el.attr('src') || '';
    // Keep video embeds (YouTube, Vimeo, etc.)
    if (/youtube|vimeo|bilibili|youku/.test(src)) return;
    auditLog.push({
      action: 'remove',
      tagName: 'iframe',
      reason: 'UNTRUSTED_IFRAME',
      confidence: 0.8,
      phase: 'pre_readability',
      snippet: src.slice(0, 80),
    });
    $el.remove();
    removedCount++;
  });

  return {
    html: $.html(),
    protectedRegions,
    removedCount,
    auditLog,
  };
}
