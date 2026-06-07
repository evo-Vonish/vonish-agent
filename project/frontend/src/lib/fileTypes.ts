/**
 * File type detection for the Workbench.
 *
 * Maps a workspace-relative path to a renderer "kind" plus, for code files, a
 * CodeMirror language id (resolved to an actual language extension in
 * `CodeEditor`). The detection is extension-based; the workbench store can
 * downgrade a tab to `binary` at load time if the backend reports the bytes
 * are not valid UTF-8.
 */

export type FileKind = 'code' | 'markdown' | 'html' | 'image' | 'pdf' | 'office' | 'binary';

export interface FileTypeInfo {
  ext: string;
  kind: FileKind;
  /** CodeMirror language id (undefined = plain text, still editable). */
  language?: string;
  /** Whether the file is editable as text in the workbench. */
  editable: boolean;
  mime?: string;
}

const IMAGE_EXT = new Set(['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'ico', 'avif']);
const OFFICE_EXT = new Set(['doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx']);

/** extension -> CodeMirror language id */
const LANGUAGE_BY_EXT: Record<string, string> = {
  js: 'javascript', mjs: 'javascript', cjs: 'javascript', jsx: 'jsx',
  ts: 'typescript', tsx: 'tsx',
  json: 'json', jsonc: 'json',
  py: 'python', pyi: 'python',
  html: 'html', htm: 'html',
  css: 'css', scss: 'css', less: 'css',
  md: 'markdown', markdown: 'markdown',
  yaml: 'yaml', yml: 'yaml',
  xml: 'xml', svg: 'xml',
  sql: 'sql',
};

const IMAGE_MIME: Record<string, string> = {
  png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp',
  gif: 'image/gif', bmp: 'image/bmp', ico: 'image/x-icon', avif: 'image/avif',
};

export function extOf(path: string): string {
  const base = path.split(/[\\/]/).pop() ?? path;
  const dot = base.lastIndexOf('.');
  return dot > 0 ? base.slice(dot + 1).toLowerCase() : '';
}

export function baseName(path: string): string {
  const clean = path.replace(/[\\/]+$/, '');
  return clean.split(/[\\/]/).pop() ?? clean;
}

export function detectFileType(path: string): FileTypeInfo {
  const ext = extOf(path);
  if (ext === 'md' || ext === 'markdown') {
    return { ext, kind: 'markdown', language: 'markdown', editable: true, mime: 'text/markdown' };
  }
  if (ext === 'html' || ext === 'htm') {
    return { ext, kind: 'html', language: 'html', editable: true, mime: 'text/html' };
  }
  if (ext === 'pdf') return { ext, kind: 'pdf', editable: false, mime: 'application/pdf' };
  if (OFFICE_EXT.has(ext)) return { ext, kind: 'office', editable: false };
  if (IMAGE_EXT.has(ext)) return { ext, kind: 'image', editable: false, mime: IMAGE_MIME[ext] };
  // Default: treat as editable text/code. The store downgrades to `binary`
  // if the backend returns base64 (non-UTF-8) bytes.
  return { ext, kind: 'code', language: LANGUAGE_BY_EXT[ext], editable: true, mime: 'text/plain' };
}
