import type { HostnameRuleEntry, SafeSelector, RuleRef, NetworkIndex, CosmeticIndex } from '../types.js';
import { PriorityLevel } from '../types.js';
import { SAFE_SELECTOR_PATTERNS, BUILTIN_AD_SELECTORS } from './safe-selectors.js';

/**
 * Calculate rule priority using AdGuard 7-level system.
 * Research ref: agent_f_final_architecture.md line 497-514, sec13.1.2
 */
export function calculatePriority(params: {
  hasTypeModifier?: boolean;
  hasDomainModifier?: boolean;
  isException?: boolean;
  isImportant?: boolean;
}): number {
  let priority = PriorityLevel.BASE;
  if (params.hasTypeModifier) priority += PriorityLevel.TYPE;
  if (params.hasDomainModifier) priority += PriorityLevel.DOMAIN;
  if (params.isException) priority += PriorityLevel.EXCEPTION;
  if (params.isImportant) priority += PriorityLevel.IMPORTANT;
  return priority;
}

/**
 * Rule Engine — manages hostname-indexed rules and safe selectors.
 *
 * Architecture (from AdGuard/uBlock research):
 * - HostnameIndex: O(1) exact hostname → rules lookup
 * - DomainSuffixIndex: prefix-based subdomain matching
 * - GenericSelectors: domain-independent safe selectors (mode-gated)
 * - Priority system: AdGuard 7-level hierarchy
 */
export class RuleEngine {
  private hostnameIndex: Map<string, string[]> = new Map();
  private domainSuffixIndex: Map<string, string[]> = new Map();
  private safeGenericSelectors: SafeSelector[] = [];
  private rulesByPriority: Map<string, RuleRef[]> = new Map();

  constructor() {
    this.safeGenericSelectors = [...SAFE_SELECTOR_PATTERNS];
  }

  /**
   * Register domain-specific selectors for a hostname with priority.
   */
  registerHostnameRules(hostname: string, selectors: string[], priorityParams?: {
    hasTypeModifier?: boolean;
    hasDomainModifier?: boolean;
    isException?: boolean;
    isImportant?: boolean;
  }): void {
    const existing = this.hostnameIndex.get(hostname) || [];
    this.hostnameIndex.set(hostname, [...existing, ...selectors]);

    // Store priority references
    const priority = calculatePriority(priorityParams || {});
    const refs = selectors.map((_s, i) => ({
      ruleId: `${hostname}_${i}`,
      priority,
      filterList: 'custom',
    }));
    const existingRefs = this.rulesByPriority.get(hostname) || [];
    this.rulesByPriority.set(hostname, [...existingRefs, ...refs].sort((a, b) => b.priority - a.priority));
  }

  /**
   * Register domain suffix rules with priority.
   */
  registerDomainSuffix(suffix: string, selectors: string[], priorityParams?: {
    hasTypeModifier?: boolean;
    hasDomainModifier?: boolean;
    isException?: boolean;
    isImportant?: boolean;
  }): void {
    const existing = this.domainSuffixIndex.get(suffix) || [];
    this.domainSuffixIndex.set(suffix, [...existing, ...selectors]);

    const priority = calculatePriority(priorityParams || {});
    const refs = selectors.map((_s, i) => ({
      ruleId: `${suffix}_${i}`,
      priority,
      filterList: 'custom',
    }));
    const existingRefs = this.rulesByPriority.get(suffix) || [];
    this.rulesByPriority.set(suffix, [...existingRefs, ...refs].sort((a, b) => b.priority - a.priority));
  }

  /**
   * Get rule references sorted by priority for a hostname.
   */
  getRuleRefs(hostname: string): RuleRef[] {
    const refs: RuleRef[] = [...(this.rulesByPriority.get(hostname) || [])];

    for (const [suffix, suffixRefs] of this.rulesByPriority) {
      if (hostname.endsWith(suffix)) {
        refs.push(...suffixRefs);
      }
    }

    return refs.sort((a, b) => b.priority - a.priority);
  }

  /**
   * Get the network index for external inspection.
   */
  getNetworkIndex(): NetworkIndex {
    return {
      hostnameIndex: new Map([...this.rulesByPriority.entries()].map(([k, v]) => [k, [...v]])),
      domainSuffixIndex: new Map(),
      genericRules: [],
    };
  }

  /**
   * Get the cosmetic index for external inspection.
   */
  getCosmeticIndex(): CosmeticIndex {
    return {
      hostnameSelectorIndex: new Map([...this.hostnameIndex.entries()].map(([k, v]) => [k, [...v]])),
      safeGenericSelectors: this.safeGenericSelectors.map(s => s.pattern.source),
      hostnameExceptionIndex: new Map(),
    };
  }

  /**
   * Load built-in rules for a specific hostname.
   * Returns combined domain-specific + builtin generic selectors.
   */
  getSelectorsForHostname(hostname: string, useGeneric: boolean): string[] {
    const selectors: string[] = [...BUILTIN_AD_SELECTORS];

    // Exact hostname match
    const exactRules = this.hostnameIndex.get(hostname);
    if (exactRules) {
      selectors.push(...exactRules);
    }

    // Domain suffix match (reverse lookup)
    for (const [suffix, rules] of this.domainSuffixIndex) {
      if (hostname.endsWith(suffix)) {
        selectors.push(...rules);
      }
    }

    // Generic safe selectors (only in balanced/aggressive modes)
    if (useGeneric) {
      for (const safe of this.safeGenericSelectors) {
        selectors.push(safe.pattern.source);
      }
    }

    return selectors;
  }

  /**
   * Get safe selector objects for confidence scoring.
   */
  getSafeSelectors(): SafeSelector[] {
    return this.safeGenericSelectors;
  }

  /**
   * Add a custom safe selector pattern.
   */
  addSafeSelector(selector: SafeSelector): void {
    this.safeGenericSelectors.push(selector);
  }

  /**
   * Add bulk hostname rule entries.
   */
  loadHostnameEntries(entries: HostnameRuleEntry[]): void {
    for (const entry of entries) {
      this.registerHostnameRules(entry.hostname, entry.selectors);
    }
  }
}
