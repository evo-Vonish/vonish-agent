import type { EvidencePack, AuditLogEntry, PurifyMode } from '../types.js';

/**
 * Assemble the EvidencePack — a complete snapshot of the purification pipeline.
 *
 * Preserves every intermediate state so any result can be traced back
 * to its original input. Used for quality monitoring and post-hoc auditing.
 *
 * Research ref: sec11.1.1, sec12.3.3, sec15.1.1
 */
export function assembleEvidencePack(params: {
  sourceUrl: string;
  originalHtml: string;
  phase1Html: string;
  extractedHtml: string;
  markdown: string;
  auditEntries: AuditLogEntry[];
  mode: PurifyMode;
}): EvidencePack {
  return {
    sourceUrl: params.sourceUrl,
    originalHtml: params.originalHtml,
    phase1Html: params.phase1Html,
    extractedHtml: params.extractedHtml,
    markdown: params.markdown,
    auditEntries: params.auditEntries,
    processedAt: new Date().toISOString(),
    mode: params.mode,
  };
}
