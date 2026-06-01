/**
 * Generate a human-readable description of a DOM element for audit logs.
 */
export function describeElement(tagName: string, className: string, id: string, text: string): string {
  const parts: string[] = [tagName.toLowerCase()];
  if (id) parts.push(`#${id}`);
  if (className) parts.push(`.${className.replace(/\s+/g, '.').slice(0, 60)}`);
  const snippet = text.trim().slice(0, 80);
  if (snippet) parts.push(`"${snippet}"`);
  return parts.join(' ');
}

/**
 * Generate a unique region ID.
 */
let _regionCounter = 0;
export function generateRegionId(): string {
  return `region_${++_regionCounter}_${Date.now().toString(36)}`;
}

/**
 * Reset region counter (for testing).
 */
export function resetRegionCounter(): void {
  _regionCounter = 0;
}
