import { Check, Sparkles, X } from 'lucide-react';
import { useProposedEditStore } from '@/stores/proposedEditStore';

/** Apply / Reject bar shown above an editor when the agent proposes an edit. */
export function ProposedEditBar({ tabId }: { tabId: string }) {
  const edit = useProposedEditStore((s) => s.edits[tabId]);
  const apply = useProposedEditStore((s) => s.apply);
  const reject = useProposedEditStore((s) => s.reject);

  if (!edit) return null;

  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-[#c66a38]/30 bg-[#1a140e] px-3 py-1.5">
      <Sparkles className="h-3.5 w-3.5 shrink-0 text-[#c66a38]" />
      <span className="min-w-0 flex-1 truncate text-[11.5px] text-[#e0a072]">AI 提议修改：{edit.summary}</span>
      <button
        onClick={() => apply(tabId)}
        className="flex items-center gap-1 rounded-md bg-[#5a8a5e]/20 px-2 py-1 text-[11px] text-[#7ec98a] transition-colors hover:bg-[#5a8a5e]/30"
      >
        <Check className="h-3.5 w-3.5" /> 应用
      </button>
      <button
        onClick={() => reject(tabId)}
        className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-[#9a9590] transition-colors hover:bg-white/[0.08]"
      >
        <X className="h-3.5 w-3.5" /> 拒绝
      </button>
    </div>
  );
}
