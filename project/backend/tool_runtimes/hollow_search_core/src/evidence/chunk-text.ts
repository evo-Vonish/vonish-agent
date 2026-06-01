/**
 * Text chunking — Paragraph-Merging Strategy.
 *
 * Splits article text into overlapping chunks by:
 * 1. Splitting on paragraph boundaries (\n\n+)
 * 2. Merging consecutive paragraphs until maxChars
 * 3. Adding overlap between adjacent chunks
 * 4. Splitting oversized chunks at sentence boundaries
 *
 * @module chunk-text
 */

import type { CrawledArticle, Chunk, ChunkResult, ChunkOptions } from './types.js';

function makeChunkId(sourceId: string, seq: number): string {
  return `chunk_${sourceId}_${seq.toString().padStart(3, '0')}`;
}

function getOverlapText(text: string, overlapChars: number): string {
  if (text.length <= overlapChars) return text;
  const cutoff = text.length - overlapChars;
  const afterCutoff = text.slice(cutoff);
  const sentenceMatch = afterCutoff.match(/^.*?[.!?]\s+/);
  if (sentenceMatch) {
    return text.slice(0, cutoff + sentenceMatch[0].length).trim();
  }
  return text.slice(-overlapChars);
}

function findParagraphStart(fullText: string, paragraph: string, searchAfter: number): number {
  const idx = fullText.indexOf(paragraph, searchAfter);
  return idx >= 0 ? idx : searchAfter;
}

function splitAtSentenceBoundary(
  text: string,
  maxChars: number,
  overlapChars: number,
  sourceId: string,
  startOffset: number,
  startSeq: number,
): Chunk[] {
  const sentences = text.split(/(?<=[.!?])\s+/).filter(s => s.trim().length > 0);
  const chunks: Chunk[] = [];
  let buffer = '';
  let bufferStart = startOffset;
  let seq = startSeq;

  for (const sent of sentences) {
    // If a single sentence exceeds maxChars, hard-split it
    if (sent.length > maxChars) {
      // Flush current buffer first
      if (buffer.trim().length > 0) {
        const trimmed = buffer.trim();
        chunks.push({
          id: makeChunkId(sourceId, seq++),
          sourceId,
          text: trimmed,
          startChar: bufferStart,
          endChar: bufferStart + trimmed.length,
          charCount: trimmed.length,
        });
        buffer = '';
      }
      // Hard-split the long sentence into maxChars pieces
      const step = Math.max(1, maxChars - overlapChars);
      for (let pos = 0; pos < sent.length; pos += step) {
        const piece = sent.slice(pos, pos + maxChars);
        const pieceStart = startOffset + pos;
        chunks.push({
          id: makeChunkId(sourceId, seq++),
          sourceId,
          text: piece,
          startChar: pieceStart,
          endChar: pieceStart + piece.length,
          charCount: piece.length,
        });
      }
      continue;
    }

    if (buffer.length > 0 && buffer.length + sent.length > maxChars) {
      const trimmed = buffer.trim();
      chunks.push({
        id: makeChunkId(sourceId, seq++),
        sourceId,
        text: trimmed,
        startChar: bufferStart,
        endChar: bufferStart + trimmed.length,
        charCount: trimmed.length,
      });
      bufferStart = startOffset + text.indexOf(sent, bufferStart + buffer.length - startOffset);
      buffer = sent;
    } else {
      buffer += (buffer ? ' ' : '') + sent;
    }
  }

  if (buffer.trim().length > 0) {
    const trimmed = buffer.trim();
    chunks.push({
      id: makeChunkId(sourceId, seq++),
      sourceId,
      text: trimmed,
      startChar: bufferStart,
      endChar: bufferStart + trimmed.length,
      charCount: trimmed.length,
    });
  }

  return chunks;
}

/**
 * Chunk a single article into overlapping text segments.
 *
 * @param article     – Source article
 * @param options     – minChars / maxChars / overlapChars
 * @param sourceId    – Stable identifier for this source
 * @returns ChunkResult with chunks and stats
 */
export function chunkText(article: CrawledArticle, options: ChunkOptions, sourceId: string): ChunkResult {
  const text = article.text || '';
  const { minChars, maxChars, overlapChars } = options;

  if (text.length === 0) {
    return { chunks: [], stats: { totalParagraphs: 0, mergedChunks: 0, splitChunks: 0 } };
  }

  // Step 1: split into paragraphs
  const paragraphs = text
    .split(/\n\n+/)
    .map(p => p.trim())
    .filter(p => p.length > 0);

  if (paragraphs.length === 0) {
    // No paragraph breaks — treat entire text as one paragraph
    paragraphs.push(text.trim());
  }

  let splitCount = 0;
  const chunks: Chunk[] = [];
  let buffer = '';
  let bufferStart = 0;
  let searchAfter = 0;
  let seq = 1;

  for (let i = 0; i < paragraphs.length; i++) {
    const para = paragraphs[i];
    const paraStart = findParagraphStart(text, para, searchAfter);
    searchAfter = paraStart + para.length;

    if (buffer.length === 0) {
      buffer = para;
      bufferStart = paraStart;
      continue;
    }

    // Try merge
    const mergedLen = buffer.length + 2 + para.length; // +2 for "\n\n"
    if (mergedLen <= maxChars) {
      buffer += '\n\n' + para;
      continue;
    }

    // Can't merge — output current buffer
    if (buffer.length >= minChars || chunks.length === 0) {
      const overlap = getOverlapText(buffer, overlapChars);
      const trimmed = buffer.trim();
      chunks.push({
        id: makeChunkId(sourceId, seq++),
        sourceId,
        text: trimmed,
        startChar: bufferStart,
        endChar: bufferStart + trimmed.length,
        charCount: trimmed.length,
      });

      // Start new buffer with overlap
      buffer = overlap + '\n\n' + para;
      bufferStart = paraStart - overlap.length;
    } else {
      // Buffer too small but can't merge — force output
      const trimmed = buffer.trim();
      chunks.push({
        id: makeChunkId(sourceId, seq++),
        sourceId,
        text: trimmed,
        startChar: bufferStart,
        endChar: bufferStart + trimmed.length,
        charCount: trimmed.length,
      });
      buffer = para;
      bufferStart = paraStart;
    }
  }

  // Output remaining buffer
  if (buffer.trim().length > 0) {
    const trimmed = buffer.trim();
    chunks.push({
      id: makeChunkId(sourceId, seq++),
      sourceId,
      text: trimmed,
      startChar: bufferStart,
      endChar: bufferStart + trimmed.length,
      charCount: trimmed.length,
    });
  }

  // Post-process: split oversized chunks at sentence boundaries
  const finalChunks: Chunk[] = [];
  for (const c of chunks) {
    if (c.charCount > maxChars * 1.2) {
      const split = splitAtSentenceBoundary(c.text, maxChars, overlapChars, sourceId, c.startChar, seq);
      seq += split.length;
      finalChunks.push(...split);
      splitCount += split.length - 1;
    } else {
      finalChunks.push(c);
    }
  }

  return {
    chunks: finalChunks,
    stats: {
      totalParagraphs: paragraphs.length,
      mergedChunks: finalChunks.length,
      splitChunks: splitCount,
    },
  };
}

/**
 * Chunk all articles into a flat list.
 *
 * @param articles – Array of crawled articles
 * @param options  – Chunk size and overlap parameters
 * @returns Flat array of chunks from all articles
 */
export function chunkAll(articles: CrawledArticle[], options: ChunkOptions): ChunkResult {
  const allChunks: Chunk[] = [];
  let totalParagraphs = 0;
  let totalSplit = 0;

  for (let i = 0; i < articles.length; i++) {
    const article = articles[i];
    const sourceId = article.id || `src_${(i + 1).toString().padStart(3, '0')}`;
    const result = chunkText(article, options, sourceId);
    allChunks.push(...result.chunks);
    totalParagraphs += result.stats.totalParagraphs;
    totalSplit += result.stats.splitChunks;
  }

  return {
    chunks: allChunks,
    stats: {
      totalParagraphs,
      mergedChunks: allChunks.length,
      splitChunks: totalSplit,
    },
  };
}
