/**
 * Soft Paywall Detector — identify soft/subscription paywalls.
 * Unlike hard paywalls (HTTP 403), soft paywalls return 200 but
 * show only a preview of the content.
 */

const PAYWALL_PATTERNS = [
  // Common soft paywall indicators
  /subscribe\s*to\s*read\s*more/i,
  /read\s*the\s*full\s*article|full\s*article\s*available/i,
  /create\s*an\s*account\s*to\s*continue/i,
  /you\s*have\s*reached\s*your\s*(free\s*)?article\s*limit/i,
  /this\s*content\s*is\s*available\s*only\s*to\s*subscribers/i,
  /sign\s*up\s*for\s*free\s*to\s*continue\s*reading/i,
  /subscribe\s*now\s*to\s*get\s*unlimited\s*access/i,
  /register\s*now\s*to\s*read\s*the\s*full\s*story/i,
  // Metered paywall
  /\d+\s*free\s*articles?\s*(left|remaining)/i,
  // Hard paywall disguised as content
  /to\s*access\s*this\s*content,?\s*please\s*(subscribe|register|log\s*in)/i,
];

const PREVIEW_RATIO_THRESHOLD = 0.15; // Content is < 15% of expected

/**
 * Detect if text is behind a soft paywall.
 */
export function detectSoftPaywall(text: string): {
  isPaywalled: boolean;
  confidence: 'high' | 'medium' | 'low';
  reason?: string;
} {
  // Direct pattern match
  for (const pattern of PAYWALL_PATTERNS) {
    if (pattern.test(text)) {
      return { isPaywalled: true, confidence: 'high', reason: 'Paywall pattern detected' };
    }
  }

  // Check if content is suspiciously short (preview)
  if (text.length > 0 && text.length < 800) {
    // Could be a preview — check for truncation indicators
    const truncationPatterns = [
      /\.{3,}\s*$/m,
      /continue\s+reading/i,
      /read\s+more/i,
    ];
    if (truncationPatterns.some((p) => p.test(text))) {
      return { isPaywalled: true, confidence: 'medium', reason: 'Truncated content (preview)' };
    }
  }

  return { isPaywalled: false, confidence: 'low' };
}

/**
 * Strip paywall content from text (remove "subscribe to continue" parts).
 */
export function stripPaywall(text: string): string {
  // Remove everything after first paywall indicator
  for (const pattern of PAYWALL_PATTERNS) {
    const match = text.match(pattern);
    if (match && match.index !== undefined) {
      return text.slice(0, match.index).trim();
    }
  }
  return text;
}
