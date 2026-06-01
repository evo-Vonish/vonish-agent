import type { CheerioAPI } from 'cheerio';
import type { AdCandidate, ModeConfig } from '../types.js';
import { calculateNoiseScore } from './deletion-validator.js';
import { SAFE_SELECTOR_PATTERNS } from '../rules/safe-selectors.js';

/**
 * Collect ad candidates from the DOM using safe selectors and heuristics.
 *
 * Two-pass approach:
 *   1. Domain-specific + builtin selectors (high confidence)
 *   2. Generic safe selectors (balanced/aggressive modes only)
 *
 * Each candidate is scored with initial noiseScore for later validation.
 */
export function collectAdCandidates(
  $: CheerioAPI,
  config: ModeConfig,
  hostname?: string,
): AdCandidate[] {
  const candidates: AdCandidate[] = [];
  const seenElements = new Set<string>();

  function addCandidate(
    $el: any,
    selector: string,
  ): void {
    // Generate a unique key for dedup
    const el = $el.get(0);
    if (!el) return;
    const key = `${el.tagName}-${$el.attr('class') || ''}-${$el.attr('id') || ''}-${$el.text().slice(0, 50)}`;
    if (seenElements.has(key)) return;
    seenElements.add(key);

    const noiseScore = calculateNoiseScore($el, $);

    candidates.push({
      selector,
      tagName: el.tagName.toLowerCase(),
      text: $el.text(),
      noiseScore,
      elementHtml: $.html($el),
    });
  }

  // Pass 1: Built-in direct selectors (always enabled)
  const builtinSelectors = getBuiltinSelectors();
  for (const selector of builtinSelectors) {
    try {
      $(selector).each((_, el) => {
        addCandidate($(el), selector);
      });
    } catch {
      // Invalid selector, skip
    }
  }

  // Pass 2: Generic safe selectors (mode-gated)
  if (config.useGenericSelectors) {
    for (const safe of SAFE_SELECTOR_PATTERNS) {
      // Convert regex patterns to Cheerio-compatible selectors where possible
      try {
        // Use attribute selectors for class/id patterns
        $('[class]').each((_, el) => {
          const $el = $(el);
          const className = $el.attr('class') || '';
          const id = $el.attr('id') || '';
          const combined = '##' + className + ' ' + id;
          if (safe.pattern.test(combined)) {
            addCandidate($el, safe.pattern.source);
          }
        });
      } catch {
        continue;
      }
    }
  }

  // Pass 3: Semantic noise tags (nav, aside, footer, header)
  $('nav, aside, footer, header').each((_, el) => {
    const $el = $(el);
    // Only tag as candidate if short (avoid removing rich header content)
    if ($el.text().length < 300) {
      addCandidate($el, el.tagName);
    }
  });

  // Sort by noise score descending
  return candidates.sort((a, b) => b.noiseScore - a.noiseScore);
}

function getBuiltinSelectors(): string[] {
  return [
    // Ad containers
    '[class*="adsbygoogle"]',
    '[id*="google_ads"]',
    '[id*="adsense"]',
    '[class*="ad-banner"]',
    '[id*="ad-banner"]',
    '[class*="ad-container"]',
    '[id*="ad-container"]',
    '[class*="ad-wrapper"]',
    '[class*="ad-slot"]',
    // Cookie
    '[class*="cookie-banner"]',
    '[class*="cookie-consent"]',
    '[class*="cookie-notice"]',
    // Subscribe / newsletter
    '[class*="subscribe-overlay"]',
    '[class*="subscribe-modal"]',
    '[class*="newsletter-subscribe"]',
    '[class*="newsletter-popup"]',
    '[class*="newsletter-signup"]',
    '[class*="email-signup"]',
    // Popups
    '[class*="popup-overlay"]',
    '[class*="modal-overlay"]',
    // Social
    '[class*="social-share"]',
    '[class*="share-button"]',
    // Related/recommended
    '[class*="related-posts"]',
    '[class*="recommended-posts"]',
    // Tracking
    '[class*="tracking-pixel"]',
    // Iframe ads
    'iframe[src*="doubleclick"]',
    'iframe[src*="ads"]',
  ];
}
