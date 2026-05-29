import { useState } from 'react';
import { ChevronDown, ChevronRight, Wrench, CheckCircle2, XCircle, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ToolCall } from '@/types';
import { formatDuration } from '@/lib/utils';

interface ToolCardProps {
  tool: ToolCall;
  className?: string;
}

export function ToolCard({ tool, className }: ToolCardProps) {
  const [expanded, setExpanded] = useState(false);

  const statusConfig: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
    pending: {
      icon: <Loader2 className="w-4 h-4 text-muted-foreground animate-spin" />,
      label: '等待中',
      color: 'text-muted-foreground border-muted/20 bg-muted/5',
    },
    running: {
      icon: <Loader2 className="w-4 h-4 text-warning animate-spin" />,
      label: '执行中',
      color: 'text-warning border-warning/20 bg-warning/5',
    },
    success: {
      icon: <CheckCircle2 className="w-4 h-4 text-success" />,
      label: '已完成',
      color: 'text-success border-success/20 bg-success/5',
    },
    error: {
      icon: <XCircle className="w-4 h-4 text-error" />,
      label: '失败',
      color: 'text-error border-error/20 bg-error/5',
    },
  };

  const config = statusConfig[tool.status];

  return (
    <div
      className={cn(
        'rounded-lg border overflow-hidden transition-all',
        config.color,
        className
      )}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          'w-full flex items-center gap-2 px-3 py-2 text-left transition-colors',
          tool.status === 'running' && 'hover:bg-warning/10',
          tool.status === 'success' && 'hover:bg-success/10',
          tool.status === 'error' && 'hover:bg-error/10'
        )}
      >
        <Wrench className="w-4 h-4 flex-shrink-0 opacity-70" />
        <span className="text-xs font-medium flex-1 truncate">
          {tool.name}
        </span>
        <span className="text-xs opacity-60 flex-shrink-0">{config.label}</span>
        {tool.duration !== undefined && (
          <span className="text-xs opacity-50 flex-shrink-0 tabular-nums">
            {formatDuration(tool.duration)}
          </span>
        )}
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 flex-shrink-0 opacity-60" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 flex-shrink-0 opacity-60" />
        )}
      </button>
      {expanded && (
        <div className="px-3 pb-3 pt-1 border-t border-current/10">
          <div className="space-y-2">
            <div>
              <span className="text-xs font-medium opacity-50">参数</span>
              <pre className="mt-1 text-xs bg-black/30 rounded p-2 overflow-x-auto">
                {JSON.stringify(tool.arguments, null, 2)}
              </pre>
            </div>
            {tool.result !== undefined && (
              <div>
                <span className="text-xs font-medium opacity-50">结果</span>
                <pre className="mt-1 text-xs bg-black/30 rounded p-2 overflow-x-auto">
                  {typeof tool.result === 'string' ? tool.result : JSON.stringify(tool.result, null, 2)}
                </pre>
              </div>
            )}
            {tool.error && (
              <div>
                <span className="text-xs font-medium text-error/70">错误</span>
                <pre className="mt-1 text-xs bg-error/10 text-error rounded p-2 overflow-x-auto">
                  {tool.error}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
