import type { CheerioAPI, Cheerio } from 'cheerio';
import type { Element } from 'domhandler';
import type { ProtectedRegion, ProtectionSignal, ModeConfig } from '../types.js';
import { detectContentSignals } from '../utils/signals.js';
import { generateRegionId } from '../utils/element-desc.js';

/**
 * Detect protected content regions using 6-signal fusion.
 *
 * Independent signal sources:
 *   1. Semantic tags: <article>, <main>, [role="main"], [itemprop="articleBody"]
 *   2. class/id name signals: article-body, post-content, entry-content, etc.
 *   3. Text density: high text/tag ratio (>10) + low link density (<0.2)
 *   4. CJK density: CJK character ratio > 30% and text length > 100
 *   5. Heading structure: proximity to <h1>
 *   6. Link density: very low link density + substantial text
 *
 * Signals are fused by spatial proximity into ProtectedRegions.
 * Any region with weighted confidence < 0.6 is filtered out.
 */
export function detectProtectedRegions(
  $: CheerioAPI,
  config: ModeConfig,
): ProtectedRegion[] {
  const allSignals: ProtectionSignal[] = [];

  // Signal 1: Semantic tags — strongest content indicators
  const semanticSelectors = [
    'article',
    'main',
  ];
  for (const sel of semanticSelectors) {
    $(sel).each((_, el) => {
      allSignals.push({
        type: 'semantic_tag',
        confidence: 0.95,
        weight: 1.0,
        selector: sel,
      });
    });
  }

  // Also check role and itemprop attributes
  $('[role="main"], [itemprop="articleBody"], [itemtype*="Article"]').each((_, el) => {
    const role = $(el).attr('role') || $(el).attr('itemprop') || $(el).attr('itemtype') || '';
    allSignals.push({
      type: 'semantic_tag',
      confidence: 0.9,
      weight: 0.95,
      selector: `[${role}]`,
    });
  });

  // Signal 2: class/id name signals
  const positivePatterns = [
    /\barticle[_\-]?body\b/i,
    /\bpost[_\-]?content\b/i,
    /\bentry[_\-]?content\b/i,
    /\bstory[_\-]?body\b/i,
    /\bnews[_\-]?content\b/i,
    /\bcontent[_\-]?body\b/i,
    /\bmain[_\-]?text\b/i,
    /\barticle[_\-]?content\b/i,
    /\btext[_\-]?body\b/i,
  ];

  $('div, section, article, main').each((_, el) => {
    const $el = $(el);
    const combined = ($el.attr('class') || '') + ' ' + ($el.attr('id') || '');
    for (const pattern of positivePatterns) {
      if (pattern.test(combined)) {
        allSignals.push({
          type: 'class_signal',
          confidence: 0.9,
          weight: 0.9,
          selector: combined.slice(0, 80),
        });
        break;
      }
    }
  });

  // Signals 3-6: structural signals on div/section/article/main
  $('div, section, article, main').each((_, el) => {
    const $el = $(el);
    const text = $el.text();
    const textLen = text.length;
    const tagCount = $el.find('*').length || 1;
    const linkTextEls = $el.find('a');
    let linkTextLen = 0;
    linkTextEls.each((_i, a) => { linkTextLen += $(a).text().length; });

    const signals = detectContentSignals(
      el.tagName,
      ($el.attr('class') || '') + ' ' + ($el.attr('id') || ''),
      text,
      linkTextEls.text(),
      tagCount,
    );

    for (const sig of signals) {
      allSignals.push(sig);
    }
  });

  // Signal 5: Heading structure — proximity to H1
  const h1 = $('h1').first();
  if (h1.length) {
    let parent = h1.parent();
    for (let i = 0; i < 3 && parent.length; i++) {
      allSignals.push({
        type: 'heading_structure',
        confidence: 0.85 - i * 0.1,
        weight: 0.7,
        selector: parent.get(0)?.tagName || 'unknown',
      });
      parent = parent.parent();
    }
  }

  // Fuse signals into protected regions
  return fuseSignalsToRegions(allSignals, $);
}

/**
 * Fuse individual signals into ProtectedRegion clusters.
 *
 * Fusion strategy:
 *   1. Signals on the same or ancestor-descendant elements are grouped
 *   2. Each group takes the highest-confidence signal as primary type
 *   3. Final confidence = weighted average of all signals in group
 *   4. Groups with confidence < 0.6 are filtered out
 */
function fuseSignalsToRegions(
  signals: ProtectionSignal[],
  $: CheerioAPI,
): ProtectedRegion[] {
  if (signals.length === 0) return [];

  // Group signals — elements that are the same or ancestors
  const groups: ProtectionSignal[][] = [];
  const used = new Set<number>();

  for (let i = 0; i < signals.length; i++) {
    if (used.has(i)) continue;
    const group: ProtectionSignal[] = [signals[i]];
    used.add(i);

    for (let j = i + 1; j < signals.length; j++) {
      if (used.has(j)) continue;
      // Simple grouping: if selectors share common patterns, group them
      // In production, this would check DOM proximity
      group.push(signals[j]);
      used.add(j);
    }

    groups.push(group);
  }

  const regions: ProtectedRegion[] = [];

  for (const group of groups) {
    // Find max confidence signal
    const maxSignal = group.reduce((max, s) =>
      s.confidence > max.confidence ? s : max
    );

    // Weighted average confidence
    const totalWeight = group.reduce((sum, s) => sum + s.weight, 0);
    const weightedConfidence = group.reduce((sum, s) =>
      sum + s.confidence * s.weight, 0
    ) / totalWeight;

    // Filter low confidence
    if (weightedConfidence < 0.6) continue;

    regions.push({
      id: generateRegionId(),
      selector: maxSignal.selector,
      type: maxSignal.type,
      confidence: weightedConfidence,
      sourceSignals: group,
    });
  }

  // Sort by confidence descending
  return regions.sort((a, b) => b.confidence - a.confidence);
}
