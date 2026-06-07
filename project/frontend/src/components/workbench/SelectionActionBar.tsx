import { Copy, MessageSquareQuote, Sparkles, X } from 'lucide-react';
import { useInlinePromptStore } from '@/stores/inlinePromptStore';
import { useReferenceStore, type NewReference } from '@/stores/referenceStore';

/**
 * Bottom inspector bar for click-selected artifact blocks (DOCX/PDF/XLSX/PPTX).
 * Offers Quote (add reference) and Ask AI (open inline prompt with instruction).
 */
export function SelectionActionBar({ label, draft, onClear }: { label: string; draft: NewReference; onClear: () => void }) {
  const addReference = useReferenceStore((s) => s.addReference);
  const openPrompt = useInlinePromptStore((s) => s.openPrompt);

  return (
    <div className="flex shrink-0 items-center gap-2 border-t border-white/[0.08] bg-[#141416] px-3 py-2">
      <span className="min-w-0 flex-1 truncate text-[11.5px] text-[#9a9590]">已选择：{label}</span>
      <button
        onClick={() => { addReference(draft); onClear(); }}
        className="flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[11.5px] text-[#e8e6e3] transition-colors hover:bg-white/[0.08]"
      >
        <MessageSquareQuote className="h-3.5 w-3.5" /> 引用
      </button>
      <button
        onClick={() => {
          openPrompt(draft, { left: Math.max(16, window.innerWidth / 2 - 170), top: Math.max(16, window.innerHeight - 250) });
          onClear();
        }}
        className="flex items-center gap-1 rounded-md bg-primary/15 px-2 py-1 text-[11.5px] text-[#e0a072] transition-colors hover:bg-primary/25"
      >
        <Sparkles className="h-3.5 w-3.5" /> 问 AI
      </button>
      <button
        onClick={() => {
          void navigator.clipboard?.writeText(draft.preview).catch(() => {});
          onClear();
        }}
        className="flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[11.5px] text-[#e8e6e3] transition-colors hover:bg-white/[0.08]"
      >
        <Copy className="h-3.5 w-3.5" /> 复制
      </button>
      <button onClick={onClear} className="rounded p-1 text-[#5c5855] transition-colors hover:bg-white/10 hover:text-[#e8e6e3]" title="取消选择">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
