import { Box, FileCode, FileText, Image as ImageIcon, MessageSquareQuote, X } from 'lucide-react';
import { cn, formatBytes } from '@/lib/utils';
import { useReferenceStore } from '@/stores/referenceStore';
import type { ReferenceSourceType } from '@/types';

interface AttachmentItem {
  id: string;
  name: string;
  type: string;
  size: number;
  uploading?: boolean;
}

interface ComposerContextBarProps {
  attachments: AttachmentItem[];
  onRemoveAttachment: (id: string) => void;
  className?: string;
}

function fileIcon(type: string) {
  if (type.startsWith('image/')) return ImageIcon;
  if (type.includes('code') || type.includes('text')) return FileCode;
  return FileText;
}

function refIcon(type: ReferenceSourceType) {
  switch (type) {
    case 'chat':
      return MessageSquareQuote;
    case 'image':
      return ImageIcon;
    case 'file-selection':
    case 'markdown-block':
    case 'artifact-block':
      return FileText;
    default:
      return Box;
  }
}

export function ComposerContextBar({ attachments, onRemoveAttachment, className }: ComposerContextBarProps) {
  const references = useReferenceStore((state) => state.references);
  const removeReference = useReferenceStore((state) => state.removeReference);
  const clearReferences = useReferenceStore((state) => state.clearReferences);
  const focusSource = useReferenceStore((state) => state.focusSource);
  if (attachments.length === 0 && references.length === 0) return null;

  return (
    <div className={cn('flex flex-wrap gap-1.5 overflow-x-auto px-3 py-2', className)}>
      {attachments.map((att) => {
        const Icon = fileIcon(att.type);
        return (
          <div key={att.id} className="group flex max-w-[260px] items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.045] py-1 pl-2 pr-1 text-[11.5px]">
            <Icon className="h-3.5 w-3.5 shrink-0 text-[#c66a38]" />
            <span className="min-w-0 truncate text-[#e8e6e3]">{att.name}</span>
            <span className="shrink-0 text-[#5c5855]">{formatBytes(att.size)}</span>
            <button
              type="button"
              onClick={() => onRemoveAttachment(att.id)}
              disabled={att.uploading}
              className="shrink-0 rounded p-0.5 text-[#5c5855] transition-colors hover:bg-white/10 hover:text-[#e8e6e3] disabled:opacity-30"
              title="移除文件"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        );
      })}
      {references.map((ref) => {
        const Icon = refIcon(ref.sourceType);
        return (
          <div key={ref.id} className="group flex max-w-[280px] items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.045] py-1 pl-2 pr-1 text-[11.5px]">
            <Icon className="h-3.5 w-3.5 shrink-0 text-[#c66a38]" />
            <button
              type="button"
              onClick={() => focusSource(ref.id)}
              title={ref.instruction ? `${ref.instruction}\n\n${ref.preview}` : ref.preview}
              className="min-w-0 flex-1 truncate text-left text-[#e8e6e3] transition-colors hover:text-white"
            >
              {ref.title}
            </button>
            {ref.instruction && <span className="shrink-0 rounded bg-[#c66a38]/20 px-1 py-px text-[9px] font-medium text-[#e0a072]">指令</span>}
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
          清除引用
        </button>
      )}
    </div>
  );
}
