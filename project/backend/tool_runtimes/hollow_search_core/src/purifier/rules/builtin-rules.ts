import type { HostnameRuleEntry } from '../types.js';

/**
 * Built-in domain-specific rules for common websites.
 * These are high-confidence, domain-targeted selectors.
 *
 * In production, these would be loaded from external rule lists.
 */
export const BUILTIN_HOSTNAME_RULES: HostnameRuleEntry[] = [
  // YouTube
  {
    hostname: 'www.youtube.com',
    selectors: [
      'ytd-display-ad-renderer',
      'ytd-action-companion-ad-renderer',
    ],
  },
  // Wikipedia (very clean, but has donation banners)
  {
    hostname: 'en.wikipedia.org',
    selectors: [
      '#centralNotice',
      '[class*="frb"]',
    ],
  },
  // Common Chinese ad platforms
  {
    hostname: 'zhuanlan.zhihu.com',
    selectors: [
      '[class*="AdBanner"]',
      '[class*="ad-card"]',
    ],
  },
];

/**
 * Get built-in hostname rules combined with any custom entries.
 */
export function getBuiltinHostnameRules(): HostnameRuleEntry[] {
  return [...BUILTIN_HOSTNAME_RULES];
}
