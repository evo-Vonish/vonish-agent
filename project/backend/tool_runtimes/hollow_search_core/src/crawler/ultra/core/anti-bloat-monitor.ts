/**
 * Anti-Bloat Monitor — real-time progress tracking + deduplication + quality gating.
 *
 * Core feature: every 100 results trigger immediate print + callback.
 * No waiting for full completion.
 */

import type { CrawlResult, CrawlProgress } from '../types.js';
import { createHash } from 'crypto';

// ─── Anti-Bloat Rules ───────────────────────────────────────────

const HARD_BLOAT_PATTERNS = [
  /cookie\s*consent/i,
  /log\s*in|sign\s*in\s*to|subscribe\s*now/i,
  /©\s*\d{4}.*all\s*rights\s*reserved/i,
  /sponsored|advertisement|promoted\s*content/i,
  /under\s*construction|coming\s*soon|503\s*error/i,
  / Cloudflare |access\s*denied|blocked/i,
  /captcha|challenge|security\s*check/i,
];

const SOFT_BLOAT_PATTERNS = [
  /subscribe\s*to|newsletter|email\s*updates/i,
  /related\s*articles|you\s*might\s*like|recommended\s*for\s*you/i,
  /share\s*this|facebook|twitter.*share|linkedin/i,
  /download\s*our\s*app|get\s*the\s*app/i,
  /privacy\s*policy|terms\s*of\s*service/i,
];

// ─── Content Quality Gate ───────────────────────────────────────

export interface QualityGate {
  minChars: number;
  minWordCount: number;
  minSentenceCount: number;
}

export function passesQualityGate(
  text: string,
  gate: QualityGate,
): boolean {
  if (text.length < gate.minChars) return false;

  const words = text.split(/\s+/).filter((w) => w.length > 0);
  if (words.length < gate.minWordCount) return false;

  const sentences = text.split(/[.!?]+/).filter((s) => s.trim().length > 0);
  if (sentences.length < gate.minSentenceCount) return false;

  return true;
}

// ─── Deduplication ──────────────────────────────────────────────

/** Normalize text for dedup comparison */
function normalizeForDedup(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 5000);
}

/** FNV-1a hash for fast dedup */
function fnv1aHash(str: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16);
}

// ─── Anti-Bloat Monitor Class ───────────────────────────────────

export class AntiBloatMonitor {
  private urlSet = new Set<string>();
  private hashSet = new Set<string>();
  private results: CrawlResult[] = [];
  private batchBuffer: CrawlResult[] = [];

  // Counters
  totalQueued = 0;
  totalStarted = 0;
  totalCompleted = 0;
  totalSucceeded = 0;
  totalFailed = 0;
  totalDeduped = 0;
  totalNoisy = 0;
  totalPaywalled = 0;
  currentBatch = 0;

  // Timing
  private startTime = 0;

  // Config
  batchSize: number;
  removeDuplicates: boolean;
  qualityGate: QualityGate;
  onBatch?: (batch: CrawlResult[]) => void | Promise<void>;
  onProgress?: (progress: CrawlProgress) => void | Promise<void>;

  constructor(opts: {
    batchSize?: number;
    removeDuplicates?: boolean;
    qualityGate?: QualityGate;
    onBatch?: (batch: CrawlResult[]) => void | Promise<void>;
    onProgress?: (progress: CrawlProgress) => void | Promise<void>;
  }) {
    this.batchSize = opts.batchSize ?? 100;
    this.removeDuplicates = opts.removeDuplicates ?? true;
    this.qualityGate = opts.qualityGate ?? {
      minChars: 200,
      minWordCount: 50,
      minSentenceCount: 3,
    };
    this.onBatch = opts.onBatch;
    this.onProgress = opts.onProgress;
  }

  start(totalQueued: number): void {
    this.startTime = Date.now();
    this.totalQueued = totalQueued;
  }

  /** Check if URL already seen */
  isDuplicateUrl(url: string): boolean {
    return this.urlSet.has(url);
  }

  /** Mark URL as queued */
  markUrlQueued(url: string): void {
    this.urlSet.add(url);
  }

  /** Check text for bloat patterns */
  checkBloat(text: string): { isBloat: boolean; bloatType?: string } {
    for (const pattern of HARD_BLOAT_PATTERNS) {
      if (pattern.test(text)) {
        return { isBloat: true, bloatType: 'hard' };
      }
    }
    for (const pattern of SOFT_BLOAT_PATTERNS) {
      if (pattern.test(text)) {
        return { isBloat: true, bloatType: 'soft' };
      }
    }
    return { isBloat: false };
  }

  /** Check content hash duplicate */
  isContentDuplicate(text: string): boolean {
    if (!this.removeDuplicates) return false;
    const normalized = normalizeForDedup(text);
    const hash = fnv1aHash(normalized);
    if (this.hashSet.has(hash)) return true;
    this.hashSet.add(hash);
    return false;
  }

  /** Process a completed result — apply dedup + bloat filtering */
  async processResult(result: CrawlResult): Promise<CrawlResult> {
    this.totalCompleted++;

    // Update status counters
    if (result.status === 'success') this.totalSucceeded++;
    else if (result.status === 'failed' || result.status === 'timeout' || result.status === 'unreachable')
      this.totalFailed++;

    // Check bloat
    const bloatCheck = this.checkBloat(result.text);
    if (bloatCheck.isBloat && bloatCheck.bloatType === 'hard') {
      result.status = 'noisy';
      this.totalNoisy++;
    }

    // Check content duplicate
    if (result.status === 'success' && this.isContentDuplicate(result.text)) {
      result.status = 'deduped';
      this.totalDeduped++;
    }

    // Check quality gate
    if (
      result.status === 'success' &&
      !passesQualityGate(result.text, this.qualityGate)
    ) {
      result.status = 'noisy';
      this.totalNoisy++;
    }

    // Add to batch buffer
    this.batchBuffer.push(result);

    // ─── KEY FEATURE: every 100 results → immediate flush ───
    if (this.batchBuffer.length >= this.batchSize) {
      await this.flushBatch();
    }

    // Progress callback
    await this.emitProgress();

    return result;
  }

  /** Flush current batch buffer */
  private async flushBatch(): Promise<void> {
    if (this.batchBuffer.length === 0) return;

    this.currentBatch++;
    const batch = [...this.batchBuffer];
    this.results.push(...batch);
    this.batchBuffer = [];

    // Print to console (anti-bloat: user sees progress every 100)
    const p = this.getProgress();
    console.log(
      `[驱虫 #${this.currentBatch}] 完成:${p.totalCompleted}/${p.totalQueued} ` +
        `成功:${p.totalSucceeded} 失败:${p.totalFailed} ` +
        `去重:${p.totalDeduped} 噪声:${p.totalNoisy} ` +
        `耗时:${p.elapsedMs}ms 速度:${p.throughputPerSecond.toFixed(1)}/s`,
    );

    // Callback
    if (this.onBatch) {
      await this.onBatch(batch);
    }
  }

  /** Emit progress callback */
  private async emitProgress(): Promise<void> {
    if (!this.onProgress) return;
    await this.onProgress(this.getProgress());
  }

  /** Get current progress snapshot */
  getProgress(): CrawlProgress {
    const elapsed = this.startTime > 0 ? Date.now() - this.startTime : 0;
    const completed = this.totalCompleted;
    const throughput = elapsed > 0 ? (completed / elapsed) * 1000 : 0;
    const remaining =
      completed > 0
        ? (this.totalQueued - completed) / (completed / elapsed)
        : 0;

    return {
      totalQueued: this.totalQueued,
      totalStarted: this.totalStarted,
      totalCompleted: completed,
      totalSucceeded: this.totalSucceeded,
      totalFailed: this.totalFailed,
      totalDeduped: this.totalDeduped,
      totalNoisy: this.totalNoisy,
      totalPaywalled: this.totalPaywalled,
      currentBatch: this.currentBatch,
      elapsedMs: elapsed,
      estimatedRemainingMs: Math.max(0, remaining),
      throughputPerSecond: throughput,
    };
  }

  /** Final flush — call at end of crawl */
  async finalize(): Promise<CrawlResult[]> {
    await this.flushBatch();
    await this.emitProgress();
    return this.results;
  }
}
