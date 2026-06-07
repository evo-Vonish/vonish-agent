import { useEffect } from 'react';
import { Copy, MessageSquareQuote, Sparkles } from 'lucide-react';
import { useSelectionStore } from '@/stores/selectionStore';
import { useReferenceStore } from '@/stores/referenceStore';
import { useInlinePromptStore } from '@/stores/inlinePromptStore';
import { getActiveSelection, popoverPosition, truncatePreview } from '@/lib/selectionRef';
import type { ReferenceSourceType } from '@/types';

/**
 * Global selection toolbar. Watches DOM text selections inside
 * `[data-quote-source]` regions (chat, markdown preview) and shows Quote / Ask AI.
 * CodeMirror selections are fed in by CodeEditor's own listener. Ctrl/Cmd+I opens
 * the inline prompt for the current selection.
 */
export function SelectionToolbar() {
  const current = useSelectionStore((s) => s.current);
  const setSelection = useSelectionStore((s) => s.setSelection);
  const addReference = useReferenceStore((s) => s.addReference);
  const openPrompt = useInlinePromptStore((s) => s.openPrompt);

  useEffect(() => {
    const onMouseUp = () => {
      const sel = getActiveSelection();
      if (!sel) return;
      const range = window.getSelection()?.getRangeAt(0);
      const node = range?.commonAncestorContainer;
      const el = node?.nodeType === Node.ELEMENT_NODE ? (node as Element) : node?.parentElement;
      if (!el || el.closest('.cm-editor')) return; // CodeMirror handles its own selection
      const host = el.closest<HTMLElement>('[data-quote-source]');
      if (!host) return;
      if (el.closest('[data-quote-card]')) return;
      const sourceType = (host.dataset.quoteSource || 'chat') as ReferenceSourceType;
      setSelection({
        origin: 'dom',
        rect: sel.rect,
        draft: {
          sourceType,
          sourceId: host.dataset.quoteMsg || undefined,
          title: truncatePreview(sel.text, 42),
          preview: truncatePreview(sel.text, 600),
          location: {
            filePath: host.dataset.quoteFile || undefined,
            workspaceId: host.dataset.quoteWs || undefined,
            messageId: host.dataset.quoteMsg || undefined,
            blockType: host.dataset.quoteBlocktype || undefined,
          },
        },
      });
    };
    const onSelChange = () => {
      const s = window.getSelection();
      if (!s || s.isCollapsed) useSelectionStore.getState().clearOrigin('dom');
    };
    document.addEventListener('mouseup', onMouseUp);
    document.addEventListener('selectionchange', onSelChange);
    return () => {
      document.removeEventListener('mouseup', onMouseUp);
      document.removeEventListener('selectionchange', onSelChange);
    };
  }, [setSelection]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'i') {
        const cur = useSelectionStore.getState().current;
        if (cur) {
          event.preventDefault();
          openPrompt(cur.draft, popoverPosition(cur.rect, 340, 150));
          setSelection(null);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [openPrompt, setSelection]);

  if (!current) return null;
  const pos = popoverPosition(current.rect, 220, 40);

  return (
    <div
      className="fixed z-[70] flex items-center gap-1 rounded-lg border border-white/[0.12] bg-[#1d1d1d] p-1 shadow-[0_10px_30px_rgba(0,0,0,0.45)]"
      style={{ left: pos.left, top: pos.top }}
      onMouseDown={(event) => event.preventDefault()}
    >
      <button
        onClick={() => {
          addReference(current.draft);
          setSelection(null);
          window.getSelection()?.removeAllRanges();
        }}
        className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-[#e8e6e3] transition-colors hover:bg-white/[0.08]"
      >
        <MessageSquareQuote className="h-3.5 w-3.5" /> 引用
      </button>
      <button
        onClick={() => {
          openPrompt(current.draft, popoverPosition(current.rect, 340, 150));
          setSelection(null);
        }}
        className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-[#e8e6e3] transition-colors hover:bg-white/[0.08]"
      >
        <Sparkles className="h-3.5 w-3.5 text-[#c66a38]" /> 问 AI
      </button>
      <button
        onClick={() => {
          void navigator.clipboard?.writeText(current.draft.preview).catch(() => {});
          setSelection(null);
          window.getSelection()?.removeAllRanges();
        }}
        className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-[#e8e6e3] transition-colors hover:bg-white/[0.08]"
      >
        <Copy className="h-3.5 w-3.5" /> 复制
      </button>
    </div>
  );
}
