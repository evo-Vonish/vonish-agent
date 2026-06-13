import { useEffect, useMemo, useRef, useState } from 'react';
import { History, LayoutGrid, Quote, RotateCcw, ShieldAlert, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import { previewWorkspaceFile, readWorkspaceFile, revertPresentation, type SlideElement, type SlideInfo } from '@/services/api';
import { useReferenceStore, type NewReference } from '@/stores/referenceStore';
import { useWorkbenchStore, type WorkbenchTab } from '@/stores/workbenchStore';
import type { DeckManifest, DeliveryGrade, ElementBox, SlideMeta, ValidatorIssue } from '@/types/ppt';
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
function issueFixDraft(tab: WorkbenchTab, slideIndex: number, issue: ValidatorIssue, el: ElementBox | null): NewReference {
  const fix = issue.suggested_fix?.action ? `（建议动作：${issue.suggested_fix.action}）` : '';
  return {
    sourceType: el ? 'slide-element' : 'slide',
    title: `${tab.title} · S${slideIndex + 1} 修复 ${issue.type}`,
    preview: (el?.text || issue.message).slice(0, 400),
    instruction: `请用 patch_presentation 修复这个问题：${issue.message}${fix}`,
    location: { filePath: tab.path, workspaceId: tab.workspaceId ?? undefined, slideIndex, elementId: el?.element_id, blockType: el?.type },
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
  reload: () => void;
}

/** Loads the sidecar deck manifest, if one exists, for a .pptx tab. */
function useDeckManifest(workspaceId: string | null | undefined, path: string | undefined): ManifestState {
  const [state, setState] = useState<Omit<ManifestState, 'reload'>>({ status: 'loading', manifest: null });
  const [nonce, setNonce] = useState(0);
  const reload = () => setNonce((n) => n + 1);
  // re-fetch when an agent patch/revert signals this artifact changed
  const externalRefresh = useWorkbenchStore((s) => s.artifactRefresh[`${workspaceId ?? ''}:${path ?? ''}`] ?? 0);

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
  }, [workspaceId, path, nonce, externalRefresh]);

  return { ...state, reload };
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
function ManifestPptxRenderer({ tab, manifest, onReverted }: { tab: WorkbenchTab; manifest: DeckManifest; onReverted: () => void }) {
  const [active, setActive] = useState(0);
  const [mode, setMode] = useState<ViewMode>('rendered');
  const [selEl, setSelEl] = useState<string | null>(null);
  const [reverting, setReverting] = useState<string | null>(null);
  const [revertError, setRevertError] = useState<string | null>(null);
  const [showIssues, setShowIssues] = useState(true);
  const [inspectorTab, setInspectorTab] = useState<'issues' | 'element' | 'versions'>('issues');
  const addReference = useReferenceStore((s) => s.addReference);
  const reveal = useWorkbenchStore((s) => (s.reveal && s.reveal.tabId === tab.id ? s.reveal : null));

  const versions = manifest.versions ?? [];
  const visualFails = (manifest.visual_findings ?? []).filter((f) => !f.ok).length;

  async function handleRevert(versionId: string) {
    if (!tab.workspaceId || !tab.path || reverting) return;
    setReverting(versionId);
    setRevertError(null);
    try {
      await revertPresentation(tab.workspaceId, tab.path, versionId);
      onReverted(); // re-fetch manifest -> parent remounts with fresh previews
    } catch (err) {
      setRevertError(err instanceof Error ? err.message : '回退失败');
      setReverting(null);
    }
  }

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

  // issues for the active slide + a quick element->severity lookup for the overlay
  const slideIdx = preview?.slide_index ?? activeIdx;
  const slideIssues = useMemo(
    () => (manifest.validation?.issues ?? []).filter((i) => i.slide_index === slideIdx),
    [manifest.validation, slideIdx],
  );
  const issueSeverityByElement = useMemo(() => {
    const map = new Map<string, 'error' | 'warning'>();
    for (const i of slideIssues) {
      const ids = [i.element_id, ...(i.element_ids ?? [])].filter(Boolean) as string[];
      for (const id of ids) {
        const prev = map.get(id);
        if (i.severity === 'error' || prev !== 'error') map.set(id, i.severity === 'error' ? 'error' : 'warning');
      }
    }
    return map;
  }, [slideIssues]);
  const elementById = (id: string | null | undefined) => meta?.elements.find((e) => e.element_id === id) ?? null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* validation header strip */}
      <div className="flex shrink-0 items-center gap-2 border-b border-white/[0.06] bg-[#0c0c0d] px-3 py-1.5 text-[11px]">
        <GradeBadge grade={grade} />
        <span className="text-[#c0554d]">{errors} 错误</span>
        <span className="text-[#b8933e]">{warnings} 警告</span>
        {autoFixed > 0 && <span className="text-[#7fd6a0]">{autoFixed} 自动修复</span>}
        {visualFails > 0 && <span className="text-[#e3bd6a]" title="L2 视觉检查未通过项">· {visualFails} 视觉</span>}
        {!manifest.validation?.deliverable && <span className="text-[#e58c87]">· 不可交付</span>}
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setShowIssues((v) => !v)}
            title="在渲染图上标注问题元素"
            className={cn('rounded-md border px-2 py-0.5 text-[11px] transition-colors',
              showIssues ? 'border-[#c66a38]/60 bg-[#c66a38]/10 text-[#e8b08a]' : 'border-white/10 text-[#9a9590] hover:bg-white/[0.06]')}
          >
            问题{slideIssues.length > 0 ? ` ${slideIssues.length}` : ''}
          </button>
          {/* version history / rollback */}
          {versions.length > 1 && (
            <div className="flex items-center gap-1" title="版本历史 / 回退">
              <History className="h-3 w-3 text-[#9a9590]" />
              <select
                value=""
                disabled={!!reverting}
                onChange={(e) => { if (e.target.value) void handleRevert(e.target.value); }}
                className="max-w-[150px] rounded border border-white/10 bg-[#16161a] px-1 py-0.5 text-[11px] text-[#c8c4be] outline-none disabled:opacity-50"
              >
                <option value="">{reverting ? `回退中…` : `历史 (${versions.length})`}</option>
                {[...versions].reverse().map((v) => (
                  <option key={v.version_id} value={v.version_id}>
                    {v.version_id} · {v.kind}{v.label ? ` · ${v.label.slice(0, 16)}` : ''}
                  </option>
                ))}
              </select>
              {reverting && <RotateCcw className="h-3 w-3 animate-spin text-[#c66a38]" />}
            </div>
          )}
          <div className="flex items-center overflow-hidden rounded-md border border-white/10">
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
      </div>
      {revertError && (
        <div className="shrink-0 border-b border-[#c0524d]/30 bg-[#2a1413] px-3 py-1 text-[11px] text-[#e58c87]">回退失败：{revertError}</div>
      )}

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
              {/* clickable element hit-targets over the rendered PNG (for element-level patch) */}
              {mainPng && (meta?.elements ?? []).map((e) => (
                <button
                  key={e.element_id}
                  title={`${e.role} · ${e.element_id}`}
                  onClick={() => setSelEl((cur) => (cur === e.element_id ? null : e.element_id))}
                  className={cn(
                    'absolute rounded-[2px] transition-colors',
                    selEl === e.element_id
                      ? 'border-2 border-[#c66a38] bg-[#c66a38]/10'
                      : 'border border-transparent hover:border-[#c66a38]/50 hover:bg-[#c66a38]/[0.06]',
                  )}
                  style={{ left: `${(e.bbox[0] / sw) * 100}%`, top: `${(e.bbox[1] / sh) * 100}%`, width: `${(e.bbox[2] / sw) * 100}%`, height: `${(e.bbox[3] / sh) * 100}%` }}
                />
              ))}
              {/* issue overlay: outline elements that have validator issues */}
              {mainPng && showIssues && (meta?.elements ?? [])
                .filter((e) => issueSeverityByElement.has(e.element_id))
                .map((e) => (
                  <div
                    key={`iss-${e.element_id}`}
                    className={cn('pointer-events-none absolute rounded-[2px] border-2',
                      issueSeverityByElement.get(e.element_id) === 'error' ? 'border-[#e0524d]' : 'border-[#d8a24a]')}
                    style={{ left: `${(e.bbox[0] / sw) * 100}%`, top: `${(e.bbox[1] / sh) * 100}%`, width: `${(e.bbox[2] / sw) * 100}%`, height: `${(e.bbox[3] / sh) * 100}%` }}
                  />
                ))}
              {selected && (
                <div className="pointer-events-none absolute left-2 top-2 max-w-[60%] truncate rounded bg-black/70 px-2 py-0.5 text-[10px] text-[#e8e6e3]">
                  选中：{selected.role || selected.type} · {selected.element_id}
                </div>
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

        {/* right inspector: issues / element metadata / version history */}
        <div className="flex w-[232px] shrink-0 flex-col border-l border-white/[0.06] bg-[#0c0c0d]">
          <div className="flex shrink-0 border-b border-white/[0.06] text-[11px]">
            {([['issues', `问题 ${slideIssues.length}`], ['element', '元素'], ['versions', `版本 ${versions.length}`]] as const).map(([k, label]) => (
              <button
                key={k}
                onClick={() => setInspectorTab(k)}
                className={cn('flex-1 px-2 py-1.5 transition-colors', inspectorTab === k ? 'bg-[#16161a] text-[#e8e6e3]' : 'text-[#9a9590] hover:bg-white/[0.04]')}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2 text-[11px]">
            {inspectorTab === 'issues' && (
              slideIssues.length === 0 ? (
                <div className="px-1 py-2 text-[#7f7a74]">本页无问题 ✓</div>
              ) : (
                <div className="space-y-1.5">
                  {slideIssues.map((iss) => {
                    const el = elementById(iss.element_id);
                    return (
                      <div key={iss.id} className="rounded border border-white/[0.07] bg-[#141416] p-1.5">
                        <div className="flex items-start gap-1.5">
                          <span className={cn('mt-0.5 h-2 w-2 shrink-0 rounded-full', iss.severity === 'error' ? 'bg-[#e0524d]' : iss.severity === 'warning' ? 'bg-[#d8a24a]' : 'bg-[#6b8fb8]')} />
                          <div className="min-w-0">
                            <div className="font-medium text-[#d8d4ce]">{iss.type}{iss.auto_fixed ? ' · 已修复' : ''}</div>
                            <div className="text-[#9a9590]">{iss.message}</div>
                          </div>
                        </div>
                        <div className="mt-1 flex gap-1">
                          {el && (
                            <button onClick={() => { setMode('rendered'); setSelEl(el.element_id); }} className="rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-[#c8c4be] hover:bg-white/[0.06]">定位</button>
                          )}
                          {!iss.auto_fixed && (
                            <button
                              onClick={() => { if (el) setSelEl(el.element_id); addReference(issueFixDraft(tab, slideIdx, iss, el)); }}
                              className="rounded border border-[#c66a38]/40 bg-[#c66a38]/10 px-1.5 py-0.5 text-[10px] text-[#e8b08a] hover:bg-[#c66a38]/20"
                            >
                              让 Agent 修复
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )
            )}
            {inspectorTab === 'element' && (
              selected ? (
                <div className="space-y-1">
                  <Meta k="id" v={selected.element_id} />
                  <Meta k="role" v={selected.role} />
                  <Meta k="type" v={selected.type} />
                  <Meta k="bbox" v={selected.bbox.map((n) => Math.round(n)).join(', ')} />
                  {selected.text && (
                    <div>
                      <div className="text-[#7f7a74]">text</div>
                      <div className="max-h-40 overflow-y-auto rounded bg-[#141416] p-1 text-[#c8c4be]">{selected.text.slice(0, 400)}</div>
                    </div>
                  )}
                  <button onClick={() => meta && addReference(metaElementDraft(tab, meta.slide_index, selected))} className="mt-1 flex items-center gap-1 rounded-md border border-white/10 px-2 py-0.5 text-[11px] text-[#e8e6e3] hover:bg-white/[0.08]">
                    <Quote className="h-3 w-3" /> 引用本元素
                  </button>
                </div>
              ) : (
                <div className="px-1 py-2 text-[#7f7a74]">点击幻灯片中的元素查看详情</div>
              )
            )}
            {inspectorTab === 'versions' && (
              <div className="space-y-1">
                {[...versions].reverse().map((v, i) => (
                  <div key={v.version_id} className="rounded border border-white/[0.07] bg-[#141416] p-1.5">
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-medium text-[#d8d4ce]">{v.version_id} · {v.kind}</span>
                      {i === 0 ? (
                        <span className="text-[10px] text-[#7fd6a0]">当前</span>
                      ) : (
                        <button disabled={!!reverting} onClick={() => void handleRevert(v.version_id)} className="rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-[#c8c4be] hover:bg-white/[0.06] disabled:opacity-40">
                          {reverting === v.version_id ? '回退中…' : '回退'}
                        </button>
                      )}
                    </div>
                    {v.label && <div className="truncate text-[#9a9590]" title={v.label}>{v.label}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {selected && meta && (
        <SelectionActionBar
          label={`Slide ${activeIdx + 1} · ${selected.role || selected.type}`}
          draft={metaElementDraft(tab, meta.slide_index, selected)}
          onClear={() => setSelEl(null)}
        />
      )}
    </div>
  );
}

function Meta({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <span className="w-10 shrink-0 text-[#7f7a74]">{k}</span>
      <span className="min-w-0 break-all text-[#c8c4be]">{v}</span>
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
  const { status, manifest, reload } = useDeckManifest(tab.workspaceId, tab.path);

  // While probing for a sidecar manifest, hold off so we don't flash the
  // structural view first. (Probe is a single readWorkspaceFile call.)
  if (status === 'loading') return <CenteredMessage spinning>加载演示文稿…</CenteredMessage>;
  if (status === 'present' && manifest) {
    // Key on created_at so a revert / re-render remounts with fresh PNG caches.
    return <ManifestPptxRenderer key={manifest.created_at || 'manifest'} tab={tab} manifest={manifest} onReverted={reload} />;
  }
  return <StructuralPptxRenderer tab={tab} />;
}
