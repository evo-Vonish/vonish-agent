import { useEffect, useMemo, useRef } from 'react';
import CodeMirror, { EditorView, type ReactCodeMirrorRef } from '@uiw/react-codemirror';
import { vscodeDark } from '@uiw/codemirror-theme-vscode';
import { javascript } from '@codemirror/lang-javascript';
import { python } from '@codemirror/lang-python';
import { json } from '@codemirror/lang-json';
import { html } from '@codemirror/lang-html';
import { css } from '@codemirror/lang-css';
import { markdown } from '@codemirror/lang-markdown';
import { yaml } from '@codemirror/lang-yaml';
import { xml } from '@codemirror/lang-xml';
import { sql } from '@codemirror/lang-sql';
import type { Extension } from '@codemirror/state';
import { useSelectionStore } from '@/stores/selectionStore';

const MONO = "'JetBrains Mono', ui-monospace, 'SF Mono', 'Cascadia Code', 'Fira Code', monospace";

function languageExtension(language?: string): Extension[] {
  switch (language) {
    case 'javascript': return [javascript()];
    case 'jsx': return [javascript({ jsx: true })];
    case 'typescript': return [javascript({ typescript: true })];
    case 'tsx': return [javascript({ jsx: true, typescript: true })];
    case 'json': return [json()];
    case 'python': return [python()];
    case 'html': return [html()];
    case 'css': return [css()];
    case 'markdown': return [markdown()];
    case 'yaml': return [yaml()];
    case 'xml': return [xml()];
    case 'sql': return [sql()];
    default: return [];
  }
}

const baseTheme = EditorView.theme({
  '&': { height: '100%', backgroundColor: 'transparent', fontSize: '12.5px' },
  '.cm-scroller': { fontFamily: MONO, lineHeight: '1.6' },
  '.cm-gutters': { backgroundColor: 'transparent', borderRight: '1px solid rgba(255,255,255,0.05)' },
  '&.cm-focused': { outline: 'none' },
});

export interface QuoteSource {
  filePath: string;
  title: string;
  workspaceId?: string | null;
}

/** Feeds CodeMirror selections (with line ranges) into the global selection store. */
function quoteListener(quoteSource: QuoteSource): Extension {
  return EditorView.updateListener.of((update) => {
    if (!update.selectionSet && !update.docChanged && !update.focusChanged) return;
    const view = update.view;
    const range = view.state.selection.main;
    const text = range.empty ? '' : view.state.sliceDoc(range.from, range.to);
    if (!text.trim()) {
      useSelectionStore.getState().clearOrigin(quoteSource.filePath);
      return;
    }
    const startLine = view.state.doc.lineAt(range.from).number;
    const endLine = view.state.doc.lineAt(range.to).number;
    const coords = view.coordsAtPos(range.head) ?? view.coordsAtPos(range.from);
    useSelectionStore.getState().setSelection({
      origin: quoteSource.filePath,
      rect: coords ? { left: coords.left, top: coords.top, bottom: coords.bottom, right: coords.right } : null,
      draft: {
        sourceType: 'file-selection',
        title: `${quoteSource.title} L${startLine}-${endLine}`,
        preview: text.length > 600 ? `${text.slice(0, 600)}…` : text,
        location: {
          filePath: quoteSource.filePath,
          workspaceId: quoteSource.workspaceId ?? undefined,
          lineStart: startLine,
          lineEnd: endLine,
        },
      },
    });
  });
}

export interface CodeEditorReveal {
  lineStart?: number;
  lineEnd?: number;
  token: number;
}

export interface CodeEditorProps {
  value: string;
  onChange?: (value: string) => void;
  language?: string;
  readOnly?: boolean;
  className?: string;
  reveal?: CodeEditorReveal | null;
  quoteSource?: QuoteSource;
}

export function CodeEditor({ value, onChange, language, readOnly, className, reveal, quoteSource }: CodeEditorProps) {
  const ref = useRef<ReactCodeMirrorRef>(null);
  const extensions = useMemo(
    () => [baseTheme, ...languageExtension(language), ...(quoteSource ? [quoteListener(quoteSource)] : [])],
    [language, quoteSource?.filePath, quoteSource?.title, quoteSource?.workspaceId],
  );

  // Imperatively scroll to + select a line range when a reveal is requested.
  useEffect(() => {
    if (!reveal) return;
    const view = ref.current?.view;
    if (!view) return;
    try {
      const total = view.state.doc.lines;
      const startLine = view.state.doc.line(Math.min(Math.max(1, reveal.lineStart ?? 1), total));
      const endLine = reveal.lineEnd
        ? view.state.doc.line(Math.min(Math.max(1, reveal.lineEnd), total))
        : startLine;
      view.dispatch({
        selection: { anchor: startLine.from, head: endLine.to },
        effects: EditorView.scrollIntoView(startLine.from, { y: 'center' }),
      });
      view.focus();
    } catch {
      /* requested line is out of range — ignore */
    }
  }, [reveal]);

  return (
    <CodeMirror
      ref={ref}
      value={value}
      height="100%"
      theme={vscodeDark}
      extensions={extensions}
      editable={!readOnly}
      readOnly={readOnly}
      onChange={onChange}
      basicSetup={{
        lineNumbers: true,
        foldGutter: true,
        autocompletion: false,
        highlightActiveLine: !readOnly,
        highlightActiveLineGutter: !readOnly,
      }}
      className={className}
      style={{ height: '100%' }}
    />
  );
}
