import { useState } from 'react';
import { Maximize2, Quote, ZoomIn, ZoomOut } from 'lucide-react';
import { formatBytes } from '@/lib/utils';
import { useReferenceStore } from '@/stores/referenceStore';
import type { WorkbenchTab } from '@/stores/workbenchStore';

export function ImageRenderer({ tab }: { tab: WorkbenchTab }) {
  const [scale, setScale] = useState(1);
  const addReference = useReferenceStore((s) => s.addReference);

  const quote = () =>
    addReference({
      sourceType: 'image',
      title: tab.title,
      preview: `图片 ${tab.title}${tab.mimeType ? ` · ${tab.mimeType}` : ''}${tab.size ? ` · ${formatBytes(tab.size)}` : ''}`,
      location: { filePath: tab.path, workspaceId: tab.workspaceId ?? undefined },
    });

  if (!tab.content) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-[12px] text-[#9a9590]">
        无法预览：图片为空或超过预览大小限制{tab.size ? `（${formatBytes(tab.size)}）` : ''}。
      </div>
    );
  }

  const src = `data:${tab.mimeType ?? 'image/png'};base64,${tab.content}`;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-1 border-b border-white/[0.06] px-3 py-1.5">
        <button onClick={() => setScale((s) => Math.max(0.1, +(s - 0.25).toFixed(2)))} className="rounded-md p-1 text-[#9a9590] transition-colors hover:bg-white/[0.06] hover:text-[#e8e6e3]" title="缩小">
          <ZoomOut className="h-4 w-4" />
        </button>
        <span className="w-12 text-center font-mono-code text-[11px] text-[#9a9590]">{Math.round(scale * 100)}%</span>
        <button onClick={() => setScale((s) => Math.min(8, +(s + 0.25).toFixed(2)))} className="rounded-md p-1 text-[#9a9590] transition-colors hover:bg-white/[0.06] hover:text-[#e8e6e3]" title="放大">
          <ZoomIn className="h-4 w-4" />
        </button>
        <button onClick={() => setScale(1)} className="rounded-md p-1 text-[#9a9590] transition-colors hover:bg-white/[0.06] hover:text-[#e8e6e3]" title="重置">
          <Maximize2 className="h-4 w-4" />
        </button>
        <button onClick={quote} className="ml-auto flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-[#9a9590] transition-colors hover:bg-white/[0.06] hover:text-[#e8e6e3]" title="引用图片">
          <Quote className="h-3.5 w-3.5" /> 引用
        </button>
        {tab.size !== undefined && <span className="font-mono-code text-[10.5px] text-[#5c5855]">{formatBytes(tab.size)}</span>}
      </div>
      <div className="min-h-0 flex-1 overflow-auto bg-[#0a0a0b] p-4">
        <img
          src={src}
          alt={tab.title}
          draggable={false}
          style={{ transform: `scale(${scale})`, transformOrigin: 'top left' }}
          className="max-w-none select-none"
        />
      </div>
    </div>
  );
}
