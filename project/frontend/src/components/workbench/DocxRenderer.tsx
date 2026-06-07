import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import type { DocBlock } from '@/services/api';
import type { NewReference } from '@/stores/referenceStore';
import { useWorkbenchStore, type WorkbenchTab } from '@/stores/workbenchStore';
import { useDocumentPreview } from './useDocumentPreview';
import { SelectionActionBar } from './SelectionActionBar';
import { CenteredMessage, ErrorView, LimitationBanner } from './RendererChrome';

function blockText(block: DocBlock): string {
  if (block.type === 'table' && block.rows) return block.rows.map((row) => row.join(' | ')).join('\n');
  return block.text ?? '';
}

function blockLabel(block: DocBlock): string {
  const text = blockText(block).replace(/\s+/g, ' ').trim();
  return `${block.type}${block.level ? ` ${block.level}` : ''} · ${text.slice(0, 40)}`;
}

function docDraft(tab: WorkbenchTab, block: DocBlock): NewReference {
  return {
    sourceType: 'doc-block',
    title: `${tab.title} · ${block.type}${block.level ? ` ${block.level}` : ''}`,
    preview: blockText(block).slice(0, 600),
    location: { filePath: tab.path, workspaceId: tab.workspaceId ?? undefined, blockId: block.id, blockType: block.type },
  };
}

function DocBlockView({ block, active, onClick }: { block: DocBlock; active: boolean; onClick: () => void }) {
  const base = cn(
    'cursor-pointer rounded-md px-2 py-1 transition-colors',
    active ? 'bg-[#c66a38]/12 ring-1 ring-[#c66a38]/40' : 'hover:bg-white/[0.04]',
  );

  if (block.type === 'heading') {
    const size = block.level === 1 ? 'text-[20px]' : block.level === 2 ? 'text-[17px]' : 'text-[15px]';
    return (
      <div data-block-id={block.id} onClick={onClick} className={cn(base, 'text-[#e8e6e3]')}>
        <span className={cn(size, 'font-semibold')}>{block.text}</span>
      </div>
    );
  }
  if (block.type === 'list_item') {
    return (
      <div data-block-id={block.id} onClick={onClick} className={cn(base, 'flex gap-2 text-[14px] text-[#cfcdc9]')}>
        <span className="text-[#5c5855]">•</span>
        <span>{block.text}</span>
      </div>
    );
  }
  if (block.type === 'table' && block.rows) {
    return (
      <div data-block-id={block.id} onClick={onClick} className={base}>
        <table className="w-full border-collapse text-[12.5px]">
          <tbody>
            {block.rows.map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => (
                  <td key={ci} className="border border-white/10 px-2 py-1 text-[#cfcdc9]">{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <div data-block-id={block.id} onClick={onClick} className={cn(base, 'text-[14px] leading-6 text-[#cfcdc9]')}>
      {block.text}
    </div>
  );
}

export function DocxRenderer({ tab }: { tab: WorkbenchTab }) {
  const { data, loading } = useDocumentPreview(tab.workspaceId, tab.path);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const reveal = useWorkbenchStore((s) => (s.reveal && s.reveal.tabId === tab.id ? s.reveal : null));
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!reveal?.blockId || !containerRef.current) return;
    const el = containerRef.current.querySelector(`[data-block-id="${reveal.blockId}"]`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('ref-flash');
      window.setTimeout(() => el.classList.remove('ref-flash'), 1600);
      setSelectedId(reveal.blockId);
    }
  }, [reveal]);

  if (loading) return <CenteredMessage spinning>解析 DOCX…</CenteredMessage>;
  if (!data?.success || !data.blocks) return <ErrorView message={data?.error?.message || '无法解析 DOCX 文档'} />;

  const selected = data.blocks.find((b) => b.id === selectedId) || null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <LimitationBanner text="DOCX 预览与引用已支持；直接写入由后续 artifact 工具处理，不会静默修改原文件。" />
      <div ref={containerRef} className="min-h-0 flex-1 overflow-auto bg-[#0f0f10] px-6 py-5">
        <div className="mx-auto max-w-[720px] space-y-2.5">
          {data.blocks.length === 0 && <div className="text-[12px] text-[#5c5855]">空文档或无可提取内容。</div>}
          {data.blocks.map((block) => (
            <DocBlockView key={block.id} block={block} active={block.id === selectedId} onClick={() => setSelectedId(block.id)} />
          ))}
        </div>
      </div>
      {selected && <SelectionActionBar label={blockLabel(selected)} draft={docDraft(tab, selected)} onClear={() => setSelectedId(null)} />}
    </div>
  );
}
