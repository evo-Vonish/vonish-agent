import { useState } from 'react';
import { Check, ChevronDown, ChevronRight, Loader2, TerminalSquare, Wrench, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ToolCall } from '@/types';
import { formatDuration } from '@/lib/utils';

interface ToolCardProps {
  tool: ToolCall;
  className?: string;
}

export function ToolCard({ tool, className }: ToolCardProps) {
  const [expanded, setExpanded] = useState(false);

  const statusConfig: Record<string, { icon: React.ReactNode; label: string; color: string; title: string }> = {
    pending: {
      icon: <Loader2 className="w-4 h-4 text-muted-foreground animate-spin" />,
      label: '等待中',
      color: 'text-foreground-muted',
      title: '等待调用工具',
    },
    running: {
      icon: <Loader2 className="w-4 h-4 text-warning animate-spin" />,
      label: '执行中',
      color: 'text-foreground-muted',
      title: '正在调用工具',
    },
    success: {
      icon: <Check className="w-4 h-4 text-foreground-muted" />,
      label: '已完成',
      color: 'text-foreground-muted',
      title: '已调用工具',
    },
    error: {
      icon: <XCircle className="w-4 h-4 text-error" />,
      label: '失败',
      color: 'text-error',
      title: '工具调用失败',
    },
  };

  const config = statusConfig[tool.status];
  const icon =
    tool.name === 'shell_command' ? (
      <TerminalSquare className="w-4 h-4" />
    ) : (
      <Wrench className="w-4 h-4" />
    );

  return (
    <div className={cn('relative space-y-2 pl-9', config.color, className)}>
      {expanded && <span className="absolute left-[9px] top-7 bottom-0 w-px bg-white/14" />}
      <span className="absolute left-0 top-0 z-10 flex h-5 w-5 items-center justify-center rounded-full border border-white/12 bg-background text-foreground-muted shadow-[0_0_0_4px_hsl(var(--background))]">
        {tool.status === 'running' ? <Loader2 className="h-4 w-4 animate-spin" /> : tool.status === 'error' ? <XCircle className="h-4 w-4 text-error" /> : icon}
      </span>
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          'flex max-w-full items-center gap-2 text-left text-[15px] font-medium transition-colors hover:text-foreground',
          tool.status === 'error' && 'hover:text-error'
        )}
      >
        <span className="min-w-0 truncate">
          {config.title}
          <span className="ml-1 text-foreground-subtle">{tool.name}</span>
        </span>
        {tool.duration !== undefined && (
          <span className="text-sm opacity-60 flex-shrink-0 tabular-nums">
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
        <div className="codex-panel-reveal relative overflow-hidden rounded-[10px] bg-[#252525] text-[13px] shadow-sm">
          <div className="border-b border-white/5 px-3 py-2 text-sm text-foreground-muted">
            {tool.name === 'shell_command' ? 'Shell' : 'Tool'}
          </div>
          <div className="max-h-[360px] space-y-3 overflow-auto px-3 py-3 font-mono text-sm leading-6">
            <div>
              <span className="text-foreground-subtle">参数</span>
              <pre className="mt-1 whitespace-pre-wrap break-words text-foreground-muted">
                {JSON.stringify(tool.arguments, null, 2)}
              </pre>
            </div>
            {tool.result !== undefined && (
              <div>
                <span className="text-foreground-subtle">结果</span>
                <pre className="mt-1 whitespace-pre-wrap break-words text-foreground-muted">
                  {typeof tool.result === 'string' ? tool.result : JSON.stringify(tool.result, null, 2)}
                </pre>
              </div>
            )}
            {tool.error && (
              <div>
                <span className="text-error/70">错误</span>
                <pre className="mt-1 whitespace-pre-wrap break-words text-error">
                  {tool.error}
                </pre>
              </div>
            )}
          </div>
          <div className={cn('flex items-center justify-end gap-2 px-3 pb-2 text-sm', tool.status === 'error' ? 'text-error' : 'text-foreground-muted')}>
            {config.icon}
            <span>{config.label}</span>
          </div>
        </div>
      )}
    </div>
  );
}
