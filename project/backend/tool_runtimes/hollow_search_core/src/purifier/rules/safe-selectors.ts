import type { SafeSelector } from '../types.js';

/**
 * Safe selector patterns — low risk, can be used directly for cosmetic filtering.
 * Each pattern is validated against a set of criteria to ensure it won't match article content.
 *
 * Source: analysis of ~166K cosmetic rules from EasyList/AdGuard/uBlock.
 * Only ~15% of cosmetic selectors are safe for server-side use.
 */
export const SAFE_SELECTOR_PATTERNS: SafeSelector[] = [
  // Ad containers
  { pattern: /^#ad[_\-]?\w+/, category: 'ad', confidence: 0.9 },
  { pattern: /^\.ad[_\-]?\w+/, category: 'ad', confidence: 0.85 },
  { pattern: /^\.adsbygoogle/, category: 'ad', confidence: 0.95 },
  { pattern: /\[class\*=["']?ad[-_]?(banner|container|wrapper|slot|unit)/i, category: 'ad', confidence: 0.9 },
  { pattern: /\[id\*=["']?google[_\-]?ads/i, category: 'ad', confidence: 0.95 },
  { pattern: /\[id\*=["']?adsense/i, category: 'ad', confidence: 0.9 },
  { pattern: /\[data-ad-/i, category: 'ad', confidence: 0.85 },

  // Cookie banners
  { pattern: /\[class\*=["']?cookie[-_]?(banner|consent|notice|policy)/i, category: 'cookie', confidence: 0.9 },

  // Subscribe / newsletter
  { pattern: /\[class\*=["']?subscribe/i, category: 'subscribe', confidence: 0.85 },
  { pattern: /\[class\*=["']?newsletter/i, category: 'subscribe', confidence: 0.85 },

  // Popups / modals
  { pattern: /\[class\*=["']?popup/i, category: 'popup', confidence: 0.85 },
  { pattern: /\[id\*=["']?popup/i, category: 'popup', confidence: 0.85 },

  // Social share
  { pattern: /\[class\*=["']?social[-_]?share/i, category: 'social', confidence: 0.8 },
  { pattern: /\[class\*=["']?share[-_]?button/i, category: 'social', confidence: 0.8 },

  // Related / recommended
  { pattern: /\[class\*=["']?related[-_]?posts/i, category: 'social', confidence: 0.75 },
  { pattern: /\[class\*=["']?recommend(ed|ations)/i, category: 'social', confidence: 0.75 },

  // Comments
  { pattern: /\[class\*=["']?comment(s)?/i, category: 'comments', confidence: 0.7 },
  { pattern: /\[id\*=["']?comment(s)?/i, category: 'comments', confidence: 0.7 },
  { pattern: /\[class\*=["']?disqus/i, category: 'comments', confidence: 0.85 },

  // Tracking / analytics
  { pattern: /\[class\*=["']?tracking/i, category: 'tracking', confidence: 0.8 },

  // Sponsored
  { pattern: /\[class\*=["']?sponsor(ed|ship)?/i, category: 'ad', confidence: 0.85 },
];

/**
 * Dangerous selector patterns — skip these entirely.
 * These can match article content, causing false positives.
 */
export const DANGEROUS_SELECTOR_PATTERNS: RegExp[] = [
  /:has-text\(/i,
  /:has\([^#.]/i,
  /:matches-css/i,
  /:xpath/i,
  /:style\(/i,
  /\barticle\b(?![-_](body|content|text))/i,
  /\.content\b(?![-_](body|area|main|wrapper))/i,
  /\.main\b(?![-_](text|content))/i,
  /\bbody\b(?![-_](article|content|text|post))/i,
  /:not\([^#]/i,
];

/**
 * Built-in direct CSS selectors for common ad/noise patterns.
 * These are the most reliable and safe selectors to use server-side.
 */
export const BUILTIN_AD_SELECTORS: string[] = [
  // Google ads
  '[class*="adsbygoogle"]',
  '[id*="google_ads"]',
  '[id*="adsense"]',

  // Ad containers
  '[class*="ad-banner"]',
  '[id*="ad-banner"]',
  '[class*="ad-container"]',
  '[id*="ad-container"]',
  '[class*="ad-wrapper"]',
  '[id*="ad-wrapper"]',
  '[class*="ad-slot"]',
  '[id*="ad-slot"]',
  '[class*="ad-unit"]',

  // Cookie
  '[class*="cookie-banner"]',
  '[class*="cookie-consent"]',
  '[class*="cookie-notice"]',
  '[class*="cookie-policy"]',

  // Subscribe
  '[class*="subscribe-overlay"]',
  '[class*="subscribe-modal"]',
  '[class*="newsletter-signup"]',
  '[class*="newsletter-popup"]',

  // Popups/modals
  '[class*="popup-overlay"]',
  '[class*="modal-overlay"]',
  '[class*="lightbox-overlay"]',

  // Social
  '[class*="social-share"]',
  '[class*="share-button"]',
  '[class*="share-bar"]',

  // Related posts
  '[class*="related-posts"]',
  '[class*="recommended-posts"]',
  '[class*="you-may-like"]',

  // Tracking
  '[class*="tracking-pixel"]',
  '[id*="tracking"]',

  // Iframe ads
  'iframe[src*="doubleclick"]',
  'iframe[src*="ads"]',
  'iframe[src*="adserver"]',

  // Hidden elements (likely tracking/ads)
  '[aria-hidden="true"]:not([role])',
];

/**
 * Check if a CSS selector is safe to apply.
 */
export function isSafeSelector(selector: string): boolean {
  return !DANGEROUS_SELECTOR_PATTERNS.some(p => p.test(selector));
}
