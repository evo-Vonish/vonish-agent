import { JSDOM } from 'jsdom';
import { Readability } from '@mozilla/readability';
import type { ExtractionConfig, ExtractionResult } from '../types.js';
import { detectChineseContent } from './chinese-adaptation.js';

/**
 * Extract main content using Mozilla Readability.
 *
 * This wraps the Mozilla Readability library which implements:
 *   - Candidate scoring (comma count + text length + class weights)
 *   - Score propagation to ancestors
 *   - Top candidate selection
 *   - Sibling merging
 *   - Multi-level fallback
 *
 * On top of Mozilla's algorithm, we add:
 *   - CJK adaptive threshold (250 instead of 500)
 *   - Quality scoring
 */
export function extractContent(
  html: string,
  url: string,
  config: ExtractionConfig,
): ExtractionResult {
  const dom = new JSDOM(html, { url });

  // Add any pre-processing hints for Readability
  const doc = dom.window.document;

  // Check if content is CJK
  const bodyText = doc.body?.textContent || '';
  const adaptation = detectChineseContent(bodyText);

  const reader = new Readability(doc, {
    charThreshold: adaptation.isChinese ? Math.min(config.charThreshold, 250) : config.charThreshold,
    keepClasses: false,
    debug: false,
  });

  const article = reader.parse();

  if (!article) {
    return {
      content: '',
      title: doc.title || '',
      byline: '',
      excerpt: '',
      textLength: 0,
      qualityScore: 0,
    };
  }

  return {
    content: article.content || '',
    title: article.title || '',
    byline: article.byline || '',
    excerpt: article.excerpt || '',
    textLength: article.textContent?.length || 0,
    qualityScore: estimateQuality(article.content || '', article.textContent || ''),
  };
}

/**
 * Estimate content quality score (0-1).
 */
function estimateQuality(htmlContent: string, textContent: string): number {
  let score = 0.5;

  // Longer content = higher quality
  if (textContent.length > 2000) score += 0.2;
  else if (textContent.length > 1000) score += 0.1;
  else if (textContent.length < 200) score -= 0.2;

  // Paragraph richness
  const pCount = (htmlContent.match(/<p[\s>]/gi) || []).length;
  if (pCount >= 5) score += 0.15;
  else if (pCount >= 2) score += 0.05;

  // Headings
  const hCount = (htmlContent.match(/<h[1-6][\s>]/gi) || []).length;
  if (hCount >= 2) score += 0.1;

  // Images (if keepImages)
  const imgCount = (htmlContent.match(/<img[\s>]/gi) || []).length;
  if (imgCount >= 2) score += 0.05;

  return Math.max(0, Math.min(1, score));
}
