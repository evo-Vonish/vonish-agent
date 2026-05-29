import { X, FileText, Image, FileCode } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatBytes } from '@/lib/utils';

interface AttachmentItem {
  id: string;
  name: string;
  type: string;
  size: number;
}

interface AttachmentBarProps {
  attachments: AttachmentItem[];
  onRemove: (id: string) => void;
  className?: string;
}

function getFileIcon(type: string) {
  if (type.startsWith('image/')) return Image;
  if (type.includes('code') || type.includes('text')) return FileCode;
  return FileText;
}

export function AttachmentBar({ attachments, onRemove, className }: AttachmentBarProps) {
  if (attachments.length === 0) return null;

  return (
    <div className={cn('flex flex-wrap gap-2 px-3 py-2', className)}>
      {attachments.map((att) => {
        const Icon = getFileIcon(att.type);
        return (
          <div
            key={att.id}
            className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-surface-hover border border-border text-xs group"
          >
            <Icon className="w-3 h-3 text-foreground-subtle" />
            <span className="max-w-[100px] truncate">{att.name}</span>
            <span className="text-foreground-subtle">{formatBytes(att.size)}</span>
            <button
              onClick={() => onRemove(att.id)}
              className="p-0.5 rounded hover:bg-error/20 hover:text-error opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
