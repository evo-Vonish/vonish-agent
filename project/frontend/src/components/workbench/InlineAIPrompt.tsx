import { useEffect, useRef, useState } from 'react';
import { CornerDownLeft, Sparkles, X } from 'lucide-react';
import { useInlinePromptStore } from '@/stores/inlinePromptStore';
import { useReferenceStore } from '@/stores/referenceStore';
import { useSelectionStore } from '@/stores/selectionStore';

/**
 * Floating inline AI prompt. On submit it creates a Reference with the typed
 * instruction attached and adds it to the Reference Bar — it never modifies the
 * file directly. The user reviews and sends from the main input.
 */
export function InlineAIPrompt() {
  const open = useInlinePromptStore((s) => s.open);
  const draft = useInlinePromptStore((s) => s.draft);
  const position = useInlinePromptStore((s) => s.position);
  const close = useInlinePromptStore((s) => s.close);
  const addReference = useReferenceStore((s) => s.addReference);
  const setSelection = useSelectionStore((s) => s.setSelection);
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      setText('');
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, close]);

  if (!open || !draft || !position) return null;

  const submit = () => {
    addReference({ ...draft, instruction: text.trim() || undefined });
    setSelection(null);
    close();
    window.getSelection()?.removeAllRanges();
  };

  return (
    <div className="fixed z-[80] w-[340px]" style={{ left: position.left, top: position.top }}>
      <div className="overflow-hidden rounded-[10px] border border-white/[0.12] bg-[#1d1d1d] shadow-[0_18px_48px_rgba(0,0,0,0.5)]">
        <div className="flex items-center gap-1.5 border-b border-white/[0.06] px-3 py-1.5 text-[11px] text-[#9a9590]">
          <Sparkles className="h-3.5 w-3.5 text-[#c66a38]" />
          <span className="min-w-0 flex-1 truncate">{draft.title}</span>
          <button onClick={close} className="rounded p-0.5 text-[#5c5855] hover:bg-white/10 hover:text-[#e8e6e3]" title="关闭 (Esc)">
            <X className="h-3 w-3" />
          </button>
        </div>
        <div className="flex items-end gap-2 px-2.5 py-2">
          <textarea
            ref={inputRef}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            rows={1}
            placeholder="请输入需要改进的点 / Describe the change…"
            className="max-h-[120px] min-h-[28px] flex-1 resize-none bg-transparent py-1 text-[13px] text-[#e8e6e3] outline-none placeholder:text-[#5c5855]"
          />
          <button
            onClick={submit}
            className="mb-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-md bg-primary text-white transition-colors hover:bg-primary-hover"
            title="添加为引用 (Enter)"
          >
            <CornerDownLeft className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="px-3 pb-2 text-[10px] leading-4 text-[#5c5855]">将作为带指令的引用添加到输入框上方，由你确认后发送（不会直接修改文件）。</div>
      </div>
    </div>
  );
}
