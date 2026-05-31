import { useState } from 'react';
import { Brain, ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SmoothStreamingText } from './SmoothStreamingText';

interface ThinkingCardProps {
  content: string;
  className?: string;
  defaultExpanded?: boolean;
  summary?: string;
  status?: 'streaming' | 'complete';
}

export function ThinkingCard({ content, className, defaultExpanded = false, summary, status = 'complete' }: ThinkingCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded || status === 'streaming');

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
      {expanded && <span className="absolute left-[9px] top-7 bottom-0 w-px bg-white/14" />}
      <span className="absolute left-0 top-0 z-10 flex h-5 w-5 items-center justify-center rounded-full border border-white/12 bg-background text-foreground-muted shadow-[0_0_0_4px_hsl(var(--background))]">
        {icon}
      </span>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex max-w-full items-center gap-2 text-left text-[15px] font-medium text-foreground-muted transition-colors hover:text-foreground"
      >
        <span className="min-w-0 truncate">
          {label}
        </span>
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />
        )}
      </button>
      {expanded && (
        <div className="codex-panel-reveal rounded-[10px] bg-[#252525] px-3 py-3 text-sm leading-7 text-foreground-muted">
          <SmoothStreamingText text={content || '思考中...'} active={status === 'streaming'} chunkSize={5} />
        </div>
      )}
    </div>
  );
}
