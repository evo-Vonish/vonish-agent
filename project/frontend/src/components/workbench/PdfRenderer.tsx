import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getDocumentPage, type PdfPageInfo, type PdfPageResult } from '@/services/api';
import type { NewReference } from '@/stores/referenceStore';
import { useWorkbenchStore, type WorkbenchTab } from '@/stores/workbenchStore';
import { useDocumentPreview } from './useDocumentPreview';
import { SelectionActionBar } from './SelectionActionBar';
import { CenteredMessage, ErrorView } from './RendererChrome';

export function PdfRenderer({ tab }: { tab: WorkbenchTab }) {
  const { data, loading } = useDocumentPreview(tab.workspaceId, tab.path);
  const [page, setPage] = useState(0);
  const [zoom, setZoom] = useState(1.3);
  const [img, setImg] = useState<string | null>(null);
  const [imgLoading, setImgLoading] = useState(false);
  const [selectedBlock, setSelectedBlock] = useState<string | null>(null);
  const reveal = useWorkbenchStore((s) => (s.reveal && s.reveal.tabId === tab.id ? s.reveal : null));
  const pageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (reveal?.pageIndex != null) {
      setPage(reveal.pageIndex);
      setSelectedBlock(reveal.blockId ?? null);
    }
  }, [reveal]);

  useEffect(() => {
    let alive = true;
    if (!tab.workspaceId || !tab.path || !data?.success) return;
    setImgLoading(true);
    getDocumentPage(tab.workspaceId, tab.path, page, 2)
      .then((res: PdfPageResult) => {
        if (!alive) return;
        setImg(res.success ? res.image ?? null : null);
        setImgLoading(false);
      })
      .catch(() => {
        if (alive) {
          setImg(null);
          setImgLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [tab.workspaceId, tab.path, page, data?.success]);

  if (loading) return <CenteredMessage spinning>解析 PDF…</CenteredMessage>;
  if (!data?.success || !data.pages) return <ErrorView message={data?.error?.message || '无法解析 PDF'} />;

  const pageCount = data.pageCount ?? data.pages.length;
  const pageInfo: PdfPageInfo | undefined = data.pages[page];
  const selected = pageInfo?.blocks.find((b) => b.id === selectedBlock) || null;
  const draft: NewReference | null = selected
    ? {
        sourceType: 'pdf-selection',
        title: `${tab.title} · P${page + 1}`,
        preview: selected.text.slice(0, 600),
        location: {
          filePath: tab.path,
          workspaceId: tab.workspaceId ?? undefined,
          pageIndex: page,
          blockId: selected.id,
          bbox: selected.bbox as [number, number, number, number],
        },
      }
    : null;

  const displayWidth = (pageInfo?.width ?? 600) * zoom;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-white/[0.06] px-3 py-1.5">
        <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page <= 0} className="rounded p-1 text-[#9a9590] transition-colors hover:bg-white/[0.06] disabled:opacity-40">
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="font-mono-code text-[11px] text-[#9a9590]">{page + 1} / {pageCount}</span>
        <button onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))} disabled={page >= pageCount - 1} className="rounded p-1 text-[#9a9590] transition-colors hover:bg-white/[0.06] disabled:opacity-40">
          <ChevronRight className="h-4 w-4" />
        </button>
        <div className="mx-1 h-4 w-px bg-white/10" />
        <button onClick={() => setZoom((z) => Math.max(0.6, +(z - 0.15).toFixed(2)))} className="rounded p-1 text-[#9a9590] transition-colors hover:bg-white/[0.06]">
          <ZoomOut className="h-4 w-4" />
        </button>
        <span className="w-10 text-center font-mono-code text-[10.5px] text-[#9a9590]">{Math.round(zoom * 100)}%</span>
        <button onClick={() => setZoom((z) => Math.min(3, +(z + 0.15).toFixed(2)))} className="rounded p-1 text-[#9a9590] transition-colors hover:bg-white/[0.06]">
          <ZoomIn className="h-4 w-4" />
        </button>
        <span className="ml-2 text-[10.5px] text-[#5c5855]">点击文本块以引用</span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto bg-[#0a0a0b] p-4">
        <div ref={pageRef} className="relative mx-auto bg-white shadow-lg" style={{ width: displayWidth }}>
          {img ? (
            <img src={img} alt={`page ${page + 1}`} className="block w-full" />
          ) : (
            <div className="flex aspect-[1/1.3] items-center justify-center text-[12px] text-[#5c5855]">{imgLoading ? '渲染中…' : '无法渲染该页'}</div>
          )}
          {pageInfo?.blocks.map((b) => {
            const [x0, y0, x1, y1] = b.bbox;
            const W = pageInfo.width || 1;
            const H = pageInfo.height || 1;
            return (
              <div
                key={b.id}
                onClick={() => setSelectedBlock(b.id)}
                title={b.text.slice(0, 120)}
                className={cn(
                  'absolute cursor-pointer rounded-sm transition-colors',
                  selectedBlock === b.id ? 'bg-[#c66a38]/25 ring-1 ring-[#c66a38]/70' : 'hover:bg-[#c66a38]/12',
                )}
                style={{
                  left: `${(x0 / W) * 100}%`,
                  top: `${(y0 / H) * 100}%`,
                  width: `${((x1 - x0) / W) * 100}%`,
                  height: `${((y1 - y0) / H) * 100}%`,
                }}
              />
            );
          })}
        </div>
      </div>

      {draft && selected && (
        <SelectionActionBar label={`P${page + 1} · ${selected.text.slice(0, 40)}`} draft={draft} onClear={() => setSelectedBlock(null)} />
      )}
    </div>
  );
}
