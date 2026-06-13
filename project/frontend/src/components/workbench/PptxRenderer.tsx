import { useEffect, useMemo, useRef, useState } from 'react';
import { LayoutGrid, Quote, ShieldAlert, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import { previewWorkspaceFile, readWorkspaceFile, type SlideElement, type SlideInfo } from '@/services/api';
import { useReferenceStore, type NewReference } from '@/stores/referenceStore';
import { useWorkbenchStore, type WorkbenchTab } from '@/stores/workbenchStore';
import type { DeckManifest, DeliveryGrade, ElementBox, SlideMeta } from '@/types/ppt';
import { useDocumentPreview } from './useDocumentPreview';
import { SelectionActionBar } from './SelectionActionBar';
import { CenteredMessage, ErrorView, LimitationBanner } from './RendererChrome';

// ── reference drafts (structural element preview) ───────────────────────────
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

// ── reference drafts (manifest slides_meta) ─────────────────────────────────
function metaSlideDraft(tab: WorkbenchTab, meta: SlideMeta): NewReference {
  const body = meta.elements.map((e) => e.text).filter(Boolean).join('\n');
  return {
    sourceType: 'slide',
    title: `${tab.title} · Slide ${meta.slide_index + 1}`,
    preview: `${meta.title}\n${body}`.slice(0, 600),
    location: { filePath: tab.path, workspaceId: tab.workspaceId ?? undefined, slideIndex: meta.slide_index },
  };
}
function metaElementDraft(tab: WorkbenchTab, slideIndex: number, el: ElementBox): NewReference {
  return {
    sourceType: 'slide-element',
    title: `${tab.title} · S${slideIndex + 1} ${el.type}`,
    preview: (el.text || `[${el.type}]`).slice(0, 500),
    location: { filePath: tab.path, workspaceId: tab.workspaceId ?? undefined, slideIndex, elementId: el.element_id, blockType: el.type },
  };
}

/** Derive `<...>/deck.manifest.json` from a `<...>/deck.pptx` path. */
function manifestPathFor(path: string | undefined): string | null {
  if (!path || !path.toLowerCase().endsWith('.pptx')) return null;
  // Only the engine-produced "deck.pptx" carries a sidecar manifest.
  if (!/deck\.pptx$/i.test(path)) return null;
  return path.replace(/deck\.pptx$/i, 'deck.manifest.json');
}

interface ManifestState {
  status: 'loading' | 'present' | 'absent';
  manifest: DeckManifest | null;
}

/** Loads the sidecar deck manifest, if one exists, for a .pptx tab. */
function useDeckManifest(workspaceId: string | null | undefined, path: string | undefined): ManifestState {
  const [state, setState] = useState<ManifestState>({ status: 'loading', manifest: null });

  useEffect(() => {
    let alive = true;
    const manifestPath = manifestPathFor(path);
    if (!workspaceId || !manifestPath) {
      setState({ status: 'absent', manifest: null });
      return;
    }
    setState({ status: 'loading', manifest: null });
    readWorkspaceFile(workspaceId, manifestPath)
      .then((res) => {
        if (!alive) return;
        try {
          const parsed = JSON.parse(res.content) as DeckManifest;
          if (parsed && Array.isArray(parsed.previews)) {
            setState({ status: 'present', manifest: parsed });
          } else {
            setState({ status: 'absent', manifest: null });
          }
        } catch {
          setState({ status: 'absent', manifest: null });
        }
      })
      .catch(() => {
        if (alive) setState({ status: 'absent', manifest: null });
      });
    return () => {
      alive = false;
    };
  }, [workspaceId, path]);

  return state;
}

/** Loads a workspace PNG as a data URL, caching by path across re-renders. */
function useSlidePng(workspaceId: string | null | undefined, path: string | undefined) {
  const cache = useRef<Map<string, string>>(new Map());
  const [, force] = useState(0);

  useEffect(() => {
    let alive = true;
    if (!workspaceId || !path || cache.current.has(path)) return;
    previewWorkspaceFile(workspaceId, path)
      .then((res) => {
        if (!alive || !res?.content) return;
        const mime = res.mime_type || 'image/png';
        cache.current.set(path, `data:${mime};base64,${res.content}`);
        force((n) => n + 1);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [workspaceId, path]);

  return path ? cache.current.get(path) ?? null : null;
}

// ── validation grade styling ────────────────────────────────────────────────
const GRADE_LABEL: Record<DeliveryGrade, string> = {
  perfect: '完美',
  good: '良好',
  acceptable: '可交付',
  degraded: '降级',
  blocked: '阻断',
};
function gradeIsOk(grade: DeliveryGrade): boolean {
  return grade === 'perfect' || grade === 'good' || grade === 'acceptable';
}

function GradeBadge({ grade }: { grade: DeliveryGrade }) {
  const ok = gradeIsOk(grade);
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium',
        ok
          ? 'border-[#3f8f5f]/40 bg-[#173023] text-[#7fd6a0]'
          : grade === 'degraded'
            ? 'border-[#b8933e]/40 bg-[#2a2310] text-[#e3bd6a]'
            : 'border-[#c0524d]/40 bg-[#2a1413] text-[#e58c87]',
      )}
    >
      {ok ? <ShieldCheck className="h-3 w-3" /> : <ShieldAlert className="h-3 w-3" />}
      {GRADE_LABEL[grade] ?? grade}
    </span>
  );
}

type ViewMode = 'rendered' | 'structure';

/**
 * High-fidelity manifest-driven preview: rendered-PNG slides with a validation
 * overlay, plus a Structure mode reusing the manifest's `slides_meta` element
 * boxes for selection + 引用.
 */
function ManifestPptxRenderer({ tab, manifest }: { tab: WorkbenchTab; manifest: DeckManifest }) {
  const [active, setActive] = useState(0);
  const [mode, setMode] = useState<ViewMode>('rendered');
  const [selEl, setSelEl] = useState<string | null>(null);
  const addReference = useReferenceStore((s) => s.addReference);
  const reveal = useWorkbenchStore((s) => (s.reveal && s.reveal.tabId === tab.id ? s.reveal : null));

  // previews drive the rail; slides_meta (if present) backs Structure mode.
  const previews = manifest.previews ?? [];
  const metaByIndex = useMemo(() => {
    const map = new Map<number, SlideMeta>();
    for (const m of manifest.slides_meta ?? []) map.set(m.slide_index, m);
    return map;
  }, [manifest.slides_meta]);

  const count = previews.length;
  const activeIdx = count > 0 ? Math.min(active, count - 1) : 0;
  const preview = previews[activeIdx];
  const meta = metaByIndex.get(preview?.slide_index ?? activeIdx) ?? null;

  useEffect(() => {
    if (reveal?.slideIndex != null) {
      setActive(reveal.slideIndex);
      setSelEl(reveal.elementId ?? null);
    }
  }, [reveal]);

  const mainPng = useSlidePng(tab.workspaceId, preview?.path);

  const grade = manifest.validation?.delivery_grade ?? 'good';
  const summary = manifest.validation?.summary;
  const errors = summary?.error_count ?? 0;
  const warnings = summary?.warning_count ?? 0;
  const autoFixed = summary?.auto_fixed ?? 0;

  const sw = preview?.width || 1280;
  const sh = preview?.height || 720;
  const selected = meta?.elements.find((e) => e.element_id === selEl) ?? null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* validation header strip */}
      <div className="flex shrink-0 items-center gap-2 border-b border-white/[0.06] bg-[#0c0c0d] px-3 py-1.5 text-[11px]">
        <GradeBadge grade={grade} />
        <span className="text-[#c0554d]">{errors} 错误</span>
        <span className="text-[#b8933e]">{warnings} 警告</span>
        {autoFixed > 0 && <span className="text-[#7fd6a0]">{autoFixed} 自动修复</span>}
        {!manifest.validation?.deliverable && <span className="text-[#e58c87]">· 不可交付</span>}
        <div className="ml-auto flex items-center overflow-hidden rounded-md border border-white/10">
          <button
            onClick={() => setMode('rendered')}
            className={cn('px-2 py-0.5 text-[11px] transition-colors', mode === 'rendered' ? 'bg-[#c66a38] text-white' : 'text-[#9a9590] hover:bg-white/[0.06]')}
          >
            渲染
          </button>
          <button
            onClick={() => setMode('structure')}
            className={cn('flex items-center gap-1 px-2 py-0.5 text-[11px] transition-colors', mode === 'structure' ? 'bg-[#c66a38] text-white' : 'text-[#9a9590] hover:bg-white/[0.06]')}
          >
            <LayoutGrid className="h-3 w-3" /> 结构
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* thumbnail rail */}
        <div className="w-[152px] shrink-0 space-y-2 overflow-y-auto border-r border-white/[0.06] bg-[#0c0c0d] p-2">
          {previews.map((p, idx) => (
            <Thumbnail
              key={p.slide_id || idx}
              tab={tab}
              preview={p}
              active={idx === activeIdx}
              onClick={() => { setActive(idx); setSelEl(null); }}
            />
          ))}
        </div>

        {/* main pane */}
        <div className="min-h-0 flex-1 overflow-auto bg-[#0a0a0b] p-4">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[12px] text-[#9a9590]">Slide {activeIdx + 1} / {count}{preview?.title ? ` · ${preview.title}` : ''}</span>
            <button
              onClick={() => meta && addReference(metaSlideDraft(tab, meta))}
              disabled={!meta}
              className="flex items-center gap-1 rounded-md border border-white/10 px-2 py-0.5 text-[11px] text-[#e8e6e3] transition-colors hover:bg-white/[0.08] disabled:opacity-40"
            >
              <Quote className="h-3 w-3" /> 引用本页
            </button>
          </div>

          {mode === 'rendered' ? (
            <div className="relative mx-auto overflow-hidden rounded-sm bg-[#16161a]" style={{ width: '100%', maxWidth: 960, aspectRatio: `${sw} / ${sh}` }}>
              {mainPng ? (
                <img src={mainPng} alt={preview?.title || `Slide ${activeIdx + 1}`} className="block h-full w-full object-contain" />
              ) : (
                <div className="flex h-full items-center justify-center text-[12px] text-[#9a9590]">加载渲染图…</div>
              )}
            </div>
          ) : (
            <div className="relative mx-auto bg-white" style={{ width: '100%', maxWidth: 960, aspectRatio: `${sw} / ${sh}` }}>
              {(meta?.elements ?? []).map((e) => (
                <div
                  key={e.element_id}
                  onClick={() => setSelEl(e.element_id)}
                  className={cn(
                    'absolute cursor-pointer overflow-hidden rounded-sm border p-1 text-[11px] leading-tight',
                    selEl === e.element_id ? 'border-[#c66a38] bg-[#c66a38]/10' : 'border-transparent hover:border-[#c66a38]/40',
                    e.role === 'title' || e.type === 'title' ? 'font-semibold text-[#1a1a1a]' : 'text-[#333333]',
                  )}
                  style={{ left: `${(e.bbox[0] / sw) * 100}%`, top: `${(e.bbox[1] / sh) * 100}%`, width: `${(e.bbox[2] / sw) * 100}%`, height: `${(e.bbox[3] / sh) * 100}%` }}
                >
                  {e.text || (e.type === 'image' ? '🖼 图片' : `[${e.role}]`)}
                </div>
              ))}
              {(!meta || meta.elements.length === 0) && (
                <div className="flex h-full items-center justify-center text-[12px] text-[#9a9590]">本页无结构元数据</div>
              )}
            </div>
          )}
        </div>
      </div>

      {mode === 'structure' && selected && meta && (
        <SelectionActionBar
          label={`Slide ${activeIdx + 1} · ${selected.role || selected.type}`}
          draft={metaElementDraft(tab, meta.slide_index, selected)}
          onClear={() => setSelEl(null)}
        />
      )}
    </div>
  );
}

function Thumbnail({ tab, preview, active, onClick }: { tab: WorkbenchTab; preview: DeckManifest['previews'][number]; active: boolean; onClick: () => void }) {
  const png = useSlidePng(tab.workspaceId, preview.path);
  const sw = preview.width || 1280;
  const sh = preview.height || 720;
  return (
    <button
      onClick={onClick}
      className={cn('block w-full overflow-hidden rounded border text-left transition-colors', active ? 'border-[#c66a38]/60' : 'border-white/10 hover:border-white/20')}
    >
      <div className="relative bg-[#16161a]" style={{ width: '100%', aspectRatio: `${sw} / ${sh}` }}>
        {png ? (
          <img src={png} alt={preview.title || `Slide ${preview.slide_index + 1}`} className="block h-full w-full object-cover" />
        ) : (
          <div className="absolute inset-0 animate-pulse bg-[#1c1c20]" />
        )}
      </div>
      <div className="truncate px-1.5 py-1 text-[10px] text-[#9a9590]">{preview.slide_index + 1}. {preview.title || '—'}</div>
    </button>
  );
}

/**
 * Existing structural element preview via useDocumentPreview -> backend
 * preview_pptx. Renders bbox divs, slide thumbnails, element selection, 引用.
 * Used as the fallback when no sidecar manifest is present.
 */
function StructuralPptxRenderer({ tab }: { tab: WorkbenchTab }) {
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

export function PptxRenderer({ tab }: { tab: WorkbenchTab }) {
  const { status, manifest } = useDeckManifest(tab.workspaceId, tab.path);

  // While probing for a sidecar manifest, hold off so we don't flash the
  // structural view first. (Probe is a single readWorkspaceFile call.)
  if (status === 'loading') return <CenteredMessage spinning>加载演示文稿…</CenteredMessage>;
  if (status === 'present' && manifest) return <ManifestPptxRenderer tab={tab} manifest={manifest} />;
  return <StructuralPptxRenderer tab={tab} />;
}
