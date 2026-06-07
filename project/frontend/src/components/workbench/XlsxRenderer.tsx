import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import type { SheetInfo } from '@/services/api';
import type { NewReference } from '@/stores/referenceStore';
import { useWorkbenchStore, type WorkbenchTab } from '@/stores/workbenchStore';
import { useDocumentPreview } from './useDocumentPreview';
import { SelectionActionBar } from './SelectionActionBar';
import { CenteredMessage, ErrorView, LimitationBanner } from './RendererChrome';

interface CellRange {
  r1: number;
  c1: number;
  r2: number;
  c2: number;
}

function colName(index: number): string {
  let n = index;
  let s = '';
  do {
    s = String.fromCharCode(65 + (n % 26)) + s;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return s;
}
function a1(r: number, c: number): string {
  return `${colName(c)}${r + 1}`;
}
function norm(r: CellRange): CellRange {
  return { r1: Math.min(r.r1, r.r2), c1: Math.min(r.c1, r.c2), r2: Math.max(r.r1, r.r2), c2: Math.max(r.c1, r.c2) };
}
function rangeStr(r: CellRange): string {
  const n = norm(r);
  return n.r1 === n.r2 && n.c1 === n.c2 ? a1(n.r1, n.c1) : `${a1(n.r1, n.c1)}:${a1(n.r2, n.c2)}`;
}
function parseA1(token: string): { r: number; c: number } | null {
  const m = /^([A-Za-z]+)(\d+)$/.exec(token.trim());
  if (!m) return null;
  let c = 0;
  for (const ch of m[1].toUpperCase()) c = c * 26 + (ch.charCodeAt(0) - 64);
  return { r: parseInt(m[2], 10) - 1, c: c - 1 };
}
function parseRange(s?: string): CellRange | null {
  if (!s) return null;
  const [a, b] = s.split(':');
  const pa = parseA1(a);
  if (!pa) return null;
  const pb = b ? parseA1(b) : pa;
  if (!pb) return null;
  return { r1: pa.r, c1: pa.c, r2: pb.r, c2: pb.c };
}

export function XlsxRenderer({ tab }: { tab: WorkbenchTab }) {
  const { data, loading } = useDocumentPreview(tab.workspaceId, tab.path);
  const [sheetIdx, setSheetIdx] = useState(0);
  const [sel, setSel] = useState<CellRange | null>(null);
  const draggingRef = useRef(false);
  const reveal = useWorkbenchStore((s) => (s.reveal && s.reveal.tabId === tab.id ? s.reveal : null));

  useEffect(() => {
    const up = () => { draggingRef.current = false; };
    window.addEventListener('mouseup', up);
    return () => window.removeEventListener('mouseup', up);
  }, []);

  useEffect(() => {
    if (!data?.success || !data.sheets || !reveal?.sheetName) return;
    const idx = data.sheets.findIndex((s) => s.name === reveal.sheetName);
    if (idx >= 0) setSheetIdx(idx);
    const r = parseRange(reveal.cellRange);
    if (r) setSel(r);
  }, [reveal, data]);

  if (loading) return <CenteredMessage spinning>解析 XLSX…</CenteredMessage>;
  if (!data?.success || !data.sheets || data.sheets.length === 0) return <ErrorView message={data?.error?.message || '无法解析 XLSX'} />;

  const sheet: SheetInfo = data.sheets[Math.min(sheetIdx, data.sheets.length - 1)];
  const colCount = sheet.rows.reduce((m, r) => Math.max(m, r.length), 1);
  const n = sel ? norm(sel) : null;
  const inSel = (r: number, c: number) => (n ? r >= n.r1 && r <= n.r2 && c >= n.c1 && c <= n.c2 : false);

  let draft: NewReference | null = null;
  if (sel) {
    const nn = norm(sel);
    const vals: string[] = [];
    for (let r = nn.r1; r <= nn.r2 && r < sheet.rows.length; r += 1) {
      const row = sheet.rows[r] || [];
      vals.push(row.slice(nn.c1, nn.c2 + 1).join('\t'));
    }
    draft = {
      sourceType: 'sheet-range',
      title: `${tab.title} · ${sheet.name}!${rangeStr(sel)}`,
      preview: vals.join('\n').slice(0, 600),
      location: { filePath: tab.path, workspaceId: tab.workspaceId ?? undefined, sheetName: sheet.name, cellRange: rangeStr(sel) },
    };
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <LimitationBanner text="XLSX 预览与引用已支持；AI 编辑将以提议形式呈现（Apply/Reject），不会静默写入。" />
      <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-white/[0.06] px-2 py-1">
        {data.sheets.map((s, i) => (
          <button
            key={`${s.name}-${i}`}
            onClick={() => { setSheetIdx(i); setSel(null); }}
            className={cn('shrink-0 rounded-md px-2.5 py-1 text-[11.5px] transition-colors', i === sheetIdx ? 'bg-white/[0.08] text-[#e8e6e3]' : 'text-[#5c5855] hover:text-[#9a9590]')}
          >
            {s.name}
          </button>
        ))}
        {sel && <span className="ml-auto shrink-0 font-mono-code text-[11px] text-[#c66a38]">{sheet.name}!{rangeStr(sel)}</span>}
      </div>
      <div className="min-h-0 flex-1 overflow-auto bg-[#0c0c0d]">
        <table className="border-collapse select-none text-[12px]">
          <thead>
            <tr>
              <th className="sticky left-0 top-0 z-20 border border-white/[0.06] bg-[#161618] px-2 py-1" />
              {Array.from({ length: colCount }).map((_, c) => (
                <th key={c} className="sticky top-0 z-10 min-w-[80px] border border-white/[0.06] bg-[#161618] px-2 py-1 font-mono-code text-[10.5px] font-normal text-[#9a9590]">{colName(c)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.rows.map((row, r) => (
              <tr key={r}>
                <td className="sticky left-0 z-10 border border-white/[0.06] bg-[#161618] px-2 py-1 text-center font-mono-code text-[10.5px] text-[#9a9590]">{r + 1}</td>
                {Array.from({ length: colCount }).map((_, c) => (
                  <td
                    key={c}
                    onMouseDown={(e) => {
                      if (e.shiftKey && sel) setSel({ ...sel, r2: r, c2: c });
                      else { setSel({ r1: r, c1: c, r2: r, c2: c }); draggingRef.current = true; }
                    }}
                    onMouseEnter={() => { if (draggingRef.current) setSel((p) => (p ? { ...p, r2: r, c2: c } : { r1: r, c1: c, r2: r, c2: c })); }}
                    className={cn('min-w-[80px] max-w-[260px] truncate border border-white/[0.05] px-2 py-1 text-[#cfcdc9]', inSel(r, c) && 'bg-[#c66a38]/20 ring-1 ring-inset ring-[#c66a38]/40')}
                  >
                    {row[c] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {sheet.truncated && <div className="p-2 text-[10.5px] text-[#5c5855]">大表已截断显示（共 {sheet.maxRow} 行 × {sheet.maxCol} 列）。</div>}
      </div>
      {draft && sel && <SelectionActionBar label={`${sheet.name}!${rangeStr(sel)}`} draft={draft} onClear={() => setSel(null)} />}
    </div>
  );
}
