import { Box, Code2, FileCode, FileText, FileType2, Globe, Image as ImageIcon, MessageSquare, Presentation, Table, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useReferenceStore } from '@/stores/referenceStore';
import type { ReferenceSourceType } from '@/types';

function refIcon(type: ReferenceSourceType) {
  switch (type) {
    case 'chat': return MessageSquare;
    case 'file-selection': return FileCode;
    case 'markdown-block': return FileText;
    case 'html-element': return Code2;
    case 'pdf-selection': return FileType2;
    case 'doc-block': return FileText;
    case 'sheet-range': return Table;
    case 'slide':
    case 'slide-element': return Presentation;
    case 'image': return ImageIcon;
    case 'browser-element': return Globe;
    default: return Box;
  }
}

export function ReferenceBar({ className }: { className?: string }) {
  const references = useReferenceStore((s) => s.references);
  const removeReference = useReferenceStore((s) => s.removeReference);
  const clearReferences = useReferenceStore((s) => s.clearReferences);
  const focusSource = useReferenceStore((s) => s.focusSource);

  if (references.length === 0) return null;

  return (
    <div className={cn('mb-2 flex flex-wrap items-center gap-1.5', className)}>
      {references.map((ref) => {
        const Icon = refIcon(ref.sourceType);
        return (
          <div
            key={ref.id}
            className="group flex max-w-[280px] items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.045] py-1 pl-2 pr-1 text-[11.5px]"
          >
            <Icon className="h-3.5 w-3.5 shrink-0 text-[#c66a38]" />
            <button
              type="button"
              onClick={() => focusSource(ref.id)}
              title={ref.instruction ? `${ref.instruction}\n\n${ref.preview}` : ref.preview}
              className="min-w-0 flex-1 truncate text-left text-[#e8e6e3] transition-colors hover:text-white"
            >
              {ref.title}
            </button>
            {ref.instruction && (
              <span title={ref.instruction} className="shrink-0 rounded bg-[#c66a38]/20 px-1 py-px text-[9px] font-medium text-[#e0a072]">
                指令
              </span>
            )}
            <button
              type="button"
              onClick={() => removeReference(ref.id)}
              className="shrink-0 rounded p-0.5 text-[#5c5855] transition-colors hover:bg-white/10 hover:text-[#e8e6e3]"
              title="移除引用"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        );
      })}
      {references.length > 1 && (
        <button
          type="button"
          onClick={clearReferences}
          className="rounded-md px-2 py-1 text-[11px] text-[#5c5855] transition-colors hover:bg-white/[0.06] hover:text-[#9a9590]"
        >
          清除全部
        </button>
      )}
    </div>
  );
}
