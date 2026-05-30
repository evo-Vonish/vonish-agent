import { X, FileText, Image, FileCode, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatBytes } from '@/lib/utils';

interface AttachmentItem {
  id: string;
  name: string;
  type: string;
  size: number;
  uploading?: boolean;
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
    <div className={cn('flex gap-2 overflow-x-auto px-3 py-2', className)}>
      {attachments.map((att) => {
        const Icon = getFileIcon(att.type);
        return (
          <div
            key={att.id}
            className="group relative flex min-w-0 max-w-[220px] flex-shrink-0 items-center gap-1.5 rounded-md border border-border bg-surface-hover px-2 py-1 text-xs"
          >
            {att.uploading ? (
              <Loader2 className="h-3 w-3 flex-shrink-0 animate-spin text-primary" />
            ) : (
              <Icon className="h-3 w-3 flex-shrink-0 text-foreground-subtle" />
            )}
            <span className="min-w-0 max-w-[120px] truncate">{att.name}</span>
            <span className="text-foreground-subtle">{formatBytes(att.size)}</span>
            <button
              onClick={() => onRemove(att.id)}
              disabled={att.uploading}
              className="rounded p-0.5 opacity-70 transition-opacity hover:bg-error/20 hover:text-error group-hover:opacity-100 disabled:cursor-not-allowed disabled:opacity-30"
              aria-label={`移除 ${att.name}`}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
