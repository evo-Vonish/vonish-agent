/**
 * Evidence Pack 统一导出。
 *
 * 导出所有 Evidence Pack API：类型定义、核心处理函数以及
 * 主编排器入口。
 *
 * @module evidence
 */

// 类型导出
export * from './types.js';

// 核心函数导出
export { buildEvidencePack } from './build-evidence-pack.js';
export { chunkText, chunkAll } from './chunk-text.js';
export { scoreChunk, scoreAllChunks, extractTerms } from './score-chunk.js';
export { dedupChunks } from './dedup-chunks.js';
export { selectPassages } from './select-passages.js';
