import { useState } from 'react';
import { ChevronDown, ChevronRight, Brain } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MarkdownRenderer } from './MarkdownRenderer';

interface ThinkingCardProps {
  content: string;
  className?: string;
  defaultExpanded?: boolean;
  summary?: string;
  status?: 'streaming' | 'complete';
}

export function ThinkingCard({ content, className, defaultExpanded = false }: ThinkingCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  // Summary = first line or first 60 chars
  const summary = content.split('\n')[0].slice(0, 60) + (content.length > 60 ? '...' : '');

  return (
    <div
      className={cn(
        'rounded-lg border border-purple-500/20 bg-purple-500/5 overflow-hidden transition-all',
        className
      )}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-purple-500/10 transition-colors"
      >
        <Brain className="w-4 h-4 text-purple-400 flex-shrink-0" />
        <span className="text-xs text-purple-300 font-medium flex-1 truncate">
          {expanded ? '思考过程' : summary || '思考过程...'}
        </span>
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" />
        )}
      </button>
      {expanded && (
        <div className="px-3 pb-3 pt-1 border-t border-purple-500/10">
          <div className="text-sm text-foreground-muted leading-relaxed whitespace-pre-wrap">
            {content}
          </div>
        </div>
      )}
    </div>
  );
}
