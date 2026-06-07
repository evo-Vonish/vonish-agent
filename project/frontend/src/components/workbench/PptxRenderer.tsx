import { useEffect, useState } from 'react';
import { Quote } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { SlideElement, SlideInfo } from '@/services/api';
import { useReferenceStore, type NewReference } from '@/stores/referenceStore';
import { useWorkbenchStore, type WorkbenchTab } from '@/stores/workbenchStore';
import { useDocumentPreview } from './useDocumentPreview';
import { SelectionActionBar } from './SelectionActionBar';
import { CenteredMessage, ErrorView, LimitationBanner } from './RendererChrome';

function slideDraft(tab: WorkbenchTab, slide: SlideInfo): NewReference {
  const body = slide.elements.map((e) => e.text).filter(Boolean).join('\n');
  return {
    sourceType: 'slide',
    title: `${tab.title} · Slide ${slide.index + 1}`,
    preview: `${slide.title}\n${body}`.slice(0, 600),
    location: { filePath: tab.path, workspaceId: tab.workspaceId ?? undefined, slideIndex: slide.index },
  };
}
function elementDraft(tab: WorkbenchTab, slideIndex: number, el: SlideElement): NewReference {
  return {
    sourceType: 'slide-element',
    title: `${tab.title} · S${slideIndex + 1} ${el.type}`,
    preview: (el.text || `[${el.type}]`).slice(0, 500),
    location: { filePath: tab.path, workspaceId: tab.workspaceId ?? undefined, slideIndex, elementId: el.id, blockType: el.type },
  };
}

export function PptxRenderer({ tab }: { tab: WorkbenchTab }) {
  const { data, loading } = useDocumentPreview(tab.workspaceId, tab.path);
  const [active, setActive] = useState(0);
  const [selEl, setSelEl] = useState<string | null>(null);
  const addReference = useReferenceStore((s) => s.addReference);
  const reveal = useWorkbenchStore((s) => (s.reveal && s.reveal.tabId === tab.id ? s.reveal : null));

  useEffect(() => {
    if (reveal?.slideIndex != null) {
      setActive(reveal.slideIndex);
      setSelEl(reveal.elementId ?? null);
    }
  }, [reveal]);

  if (loading) return <CenteredMessage spinning>解析 PPTX…</CenteredMessage>;
  if (!data?.success || !data.slides || data.slides.length === 0) return <ErrorView message={data?.error?.message || '无法解析 PPTX'} />;

  const slides = data.slides;
  const slide = slides[Math.min(active, slides.length - 1)];
  const sw = slide.width || data.slideWidth || 960;
  const sh = slide.height || data.slideHeight || 540;
  const selected = slide.elements.find((e) => e.id === selEl) || null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <LimitationBanner text="PPTX 文本与结构预览、引用已支持；完整视觉渲染与直接写入由后续 artifact 工具处理。" />
      <div className="flex min-h-0 flex-1">
        <div className="w-[152px] shrink-0 space-y-2 overflow-y-auto border-r border-white/[0.06] bg-[#0c0c0d] p-2">
          {slides.map((s) => (
            <button
              key={s.index}
              onClick={() => { setActive(s.index); setSelEl(null); }}
              className={cn('block w-full overflow-hidden rounded border text-left transition-colors', s.index === active ? 'border-[#c66a38]/60' : 'border-white/10 hover:border-white/20')}
            >
              <div className="relative bg-[#16161a]" style={{ width: '100%', aspectRatio: `${sw} / ${sh}` }}>
                {s.elements.slice(0, 14).map((e) => (
                  <div
                    key={e.id}
                    className="absolute overflow-hidden text-[3px] leading-[1.1] text-[#9a9590]"
                    style={{ left: `${(e.bbox[0] / sw) * 100}%`, top: `${(e.bbox[1] / sh) * 100}%`, width: `${(e.bbox[2] / sw) * 100}%`, height: `${(e.bbox[3] / sh) * 100}%` }}
                  >
                    {e.text}
                  </div>
                ))}
              </div>
              <div className="truncate px-1.5 py-1 text-[10px] text-[#9a9590]">{s.index + 1}. {s.title}</div>
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-auto bg-[#0a0a0b] p-4">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[12px] text-[#9a9590]">Slide {active + 1} / {slides.length}</span>
            <button
              onClick={() => addReference(slideDraft(tab, slide))}
              className="flex items-center gap-1 rounded-md border border-white/10 px-2 py-0.5 text-[11px] text-[#e8e6e3] transition-colors hover:bg-white/[0.08]"
            >
              <Quote className="h-3 w-3" /> 引用本页
            </button>
          </div>
          <div className="relative mx-auto bg-white" style={{ width: '100%', maxWidth: 960, aspectRatio: `${sw} / ${sh}` }}>
            {slide.elements.map((e) => (
              <div
                key={e.id}
                onClick={() => setSelEl(e.id)}
                className={cn(
                  'absolute cursor-pointer overflow-hidden rounded-sm border p-1 text-[11px] leading-tight',
                  selEl === e.id ? 'border-[#c66a38] bg-[#c66a38]/10' : 'border-transparent hover:border-[#c66a38]/40',
                  e.type === 'title' ? 'font-semibold text-[#1a1a1a]' : 'text-[#333333]',
                )}
                style={{ left: `${(e.bbox[0] / sw) * 100}%`, top: `${(e.bbox[1] / sh) * 100}%`, width: `${(e.bbox[2] / sw) * 100}%`, height: `${(e.bbox[3] / sh) * 100}%` }}
              >
                {e.text || (e.type === 'image' ? '🖼 图片' : '')}
              </div>
            ))}
          </div>
        </div>
      </div>
      {selected && <SelectionActionBar label={`Slide ${active + 1} · ${selected.type}`} draft={elementDraft(tab, active, selected)} onClear={() => setSelEl(null)} />}
    </div>
  );
}
