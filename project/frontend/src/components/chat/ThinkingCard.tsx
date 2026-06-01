import { useId } from 'react';
import { Brain, ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SmoothStreamingText } from './SmoothStreamingText';
import { ExecutionCollapse } from './ExecutionCollapse';
import { useExecutionDisclosure } from './useExecutionDisclosure';

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

  // Summary = first line or first 60 chars
  const fallbackSummary = content.split('\n')[0].slice(0, 60) + (content.length > 60 ? '...' : '');
  const label = status === 'streaming' ? '正在思考' : summary || fallbackSummary || '已完成思考';
  const icon =
    status === 'streaming' ? (
      <Loader2 className="w-4 h-4 flex-shrink-0 animate-spin" />
    ) : (
      <Brain className="w-4 h-4 flex-shrink-0" />
    );

  return (
    <div
      className={cn(
        'relative space-y-2 pl-9',
        className
      )}
    >
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
      <button
        onClick={() => hasContent && disclosure.toggle()}
        className="flex max-w-full items-center gap-2 text-left text-[15px] font-medium text-foreground-muted transition-colors hover:text-foreground"
      >
        <span
          className="execution-title min-w-0 truncate"
          data-motion={disclosure.titleMotion}
          data-tone={disclosure.tone}
          data-kind="thinking"
        >
          {label}
        </span>
        {hasContent && (expanded ? (
          <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />
        ))}
      </button>
      <ExecutionCollapse open={expanded && hasContent}>
        <div className="codex-panel-reveal codex-detail-panel rounded-[10px] bg-[#252525] px-3 py-2.5 text-sm leading-7 text-foreground-muted">
          <SmoothStreamingText text={content || '思考中...'} active={status === 'streaming'} chunkSize={5} />
        </div>
      </ExecutionCollapse>
    </div>
  );
}
