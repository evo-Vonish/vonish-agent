import type { AuditLogEntry } from '../types.js';

/**
 * Audit logger — tracks all purification actions for transparency and debugging.
 *
 * Each entry records:
 *   - What was done (remove/protect/mark/skip)
 *   - Why (reason with confidence score)
 *   - Where (element description)
 *   - When (implicitly via ordered array)
 */
export class AuditLogger {
  private entries: AuditLogEntry[] = [];

  /**
   * Log a purification action.
   */
  log(entry: AuditLogEntry): void {
    this.entries.push(entry);
  }

  /**
   * Convenience method for remove action.
   */
  logRemove(
    tagName: string,
    selector: string,
    reason: string,
    confidence: number,
    phase: AuditLogEntry['phase'],
    snippet?: string,
    signals?: string[],
  ): void {
    this.entries.push({
      action: 'remove',
      tagName,
      selector,
      reason,
      confidence,
      phase,
      snippet,
      signals,
    });
  }

  /**
   * Convenience method for protect action.
   */
  logProtect(
    tagName: string,
    reason: string,
    confidence: number,
    phase: AuditLogEntry['phase'],
    signals?: string[],
  ): void {
    this.entries.push({
      action: 'protect',
      tagName,
      reason,
      confidence,
      phase,
      signals,
    });
  }

  /**
   * Convenience method for skip action.
   */
  logSkip(
    tagName: string,
    reason: string,
    confidence: number,
    phase: AuditLogEntry['phase'],
  ): void {
    this.entries.push({
      action: 'skip',
      tagName,
      reason,
      confidence,
      phase,
    });
  }

  /**
   * Get all entries.
   */
  getEntries(): AuditLogEntry[] {
    return this.entries;
  }

  /**
   * Get summary statistics.
   */
  getSummary(): { removed: number; protected: number; skipped: number; total: number } {
    return {
      removed: this.entries.filter(e => e.action === 'remove').length,
      protected: this.entries.filter(e => e.action === 'protect').length,
      skipped: this.entries.filter(e => e.action === 'skip').length,
      total: this.entries.length,
    };
  }

  /**
   * Reset the logger.
   */
  reset(): void {
    this.entries = [];
  }
}
