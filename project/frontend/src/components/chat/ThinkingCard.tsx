import { useId } from 'react';
import { Brain, ChevronDown, ChevronRight, Copy, Loader2, MessageSquareQuote, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SmoothStreamingText } from './SmoothStreamingText';
import { ExecutionCollapse } from './ExecutionCollapse';
import { useExecutionDisclosure } from './useExecutionDisclosure';
import { useInlinePromptStore } from '@/stores/inlinePromptStore';
import { useReferenceStore, type NewReference } from '@/stores/referenceStore';

interface ThinkingCardProps {
  id?: string;
  content: string;
  className?: string;
  defaultExpanded?: boolean;
  summary?: string;
  status?: 'streaming' | 'complete';
}

export function ThinkingCard({ id, content, className, defaultExpanded = false, summary, status = 'complete' }: ThinkingCardProps) {
  const fallbackId = useId();
  const disclosure = useExecutionDisclosure({
    id: id ?? fallbackId,
    status,
    defaultExpanded,
    defaultCollapsed: defaultExpanded ? false : undefined,
    runningStatuses: ['streaming'],
    terminalStatuses: ['complete'],
  });
  const expanded = disclosure.expanded;
  const hasContent = content.trim().length > 0;
  const addReference = useReferenceStore((state) => state.addReference);
  const openPrompt = useInlinePromptStore((state) => state.openPrompt);

  // Summary = first line or first 60 chars
  const fallbackSummary = content.split('\n')[0].slice(0, 60) + (content.length > 60 ? '...' : '');
  const label = status === 'streaming' ? '正在思考' : summary || fallbackSummary || '已完成思考';
  const draft: NewReference = {
    sourceType: 'chat',
    sourceId: id ?? fallbackId,
    title: label,
    preview: content.slice(0, 4000),
    location: { blockId: id ?? fallbackId, blockType: 'thinking' },
  };
  const icon =
    status === 'streaming' ? (
      <Loader2 className="w-4 h-4 flex-shrink-0 animate-spin" />
    ) : (
      <Brain className="w-4 h-4 flex-shrink-0" />
    );

  return (
    <div className={cn('relative space-y-2 pl-9 text-[#9a9590]', className)}>
      {expanded && (
        <span
          className={cn(
            'workflow-rail-line workflow-rail-line-short',
            status === 'streaming' && 'workflow-rail-line-thinking',
          )}
        />
      )}
      <span className={cn('workflow-rail-icon', status === 'streaming' && 'workflow-rail-icon-thinking')}>
        {icon}
      </span>
      <div className="group flex max-w-full items-center gap-2">
        <button
          type="button"
          onClick={() => hasContent && disclosure.toggle()}
          className="flex min-w-0 items-center gap-2 rounded-md py-0.5 text-left text-[14px] font-medium text-[#9a9590] transition-colors hover:text-[#e8e6e3]"
        >
          <span
            className="execution-title min-w-0 truncate"
            data-motion={disclosure.titleMotion}
            data-tone={disclosure.tone}
            data-kind="thinking"
          >
            {label}
          </span>
          {hasContent && (
            expanded ? (
              <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 text-[#5c5855] group-hover:text-[#9a9590]" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 flex-shrink-0 text-[#5c5855] group-hover:text-[#9a9590]" />
            )
          )}
        </button>
        {hasContent && (
          <span className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100" data-quote-card="thinking">
            <button type="button" onClick={() => addReference(draft)} className="rounded p-0.5 text-[#5c5855] hover:bg-white/5 hover:text-[#e8e6e3]" title="引用完整思考">
              <MessageSquareQuote className="h-3.5 w-3.5" />
            </button>
            <button type="button" onClick={() => openPrompt(draft, { left: Math.max(16, window.innerWidth / 2 - 170), top: Math.max(16, window.innerHeight - 250) })} className="rounded p-0.5 text-[#5c5855] hover:bg-white/5 hover:text-[#e0a072]" title="询问 AI">
              <Sparkles className="h-3.5 w-3.5" />
            </button>
            <button type="button" onClick={() => void navigator.clipboard?.writeText(content).catch(() => {})} className="rounded p-0.5 text-[#5c5855] hover:bg-white/5 hover:text-[#e8e6e3]" title="复制完整思考">
              <Copy className="h-3.5 w-3.5" />
            </button>
          </span>
        )}
      </div>
      <ExecutionCollapse open={expanded && hasContent}>
        <div
          className="codex-panel-reveal codex-detail-panel rounded-md px-3 py-2.5 text-sm leading-7 text-[#9a9590]"
          style={{ background: 'rgba(20, 20, 22, 0.68)', border: '1px solid rgba(255,255,255,0.06)' }}
        >
          <SmoothStreamingText text={content || '思考中...'} active={status === 'streaming'} chunkSize={5} />
        </div>
      </ExecutionCollapse>
    </div>
  );
}
