import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Code2,
  FileDiff,
  FilePlus2,
  FileText,
  Globe,
  Loader2,
  Search,
  Terminal,
  Wrench,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ExecutionSegment, ExecutionStep } from '@/types';
import { SmoothStreamingText } from './SmoothStreamingText';

interface ExecutionSegmentCardProps {
  segment: ExecutionSegment;
}

const statusLabel: Record<ExecutionSegment['status'], string> = {
  running: '处理中',
  completed: '处理完毕',
  failed: '处理失败',
  cancelled: '已取消',
  waiting_user: '等待用户',
};

function formatDuration(ms?: number) {
  if (!ms || ms < 0) return '';
  if (ms < 1000) return `${Math.max(1, Math.round(ms))}ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`;
}

function stepIcon(step: ExecutionStep) {
  const cls = 'h-3.5 w-3.5';
  if (step.status === 'running') return <Loader2 className={cn(cls, 'animate-spin')} />;
  if (step.status === 'failed') return <AlertTriangle className={cls} />;
  switch (step.type) {
    case 'thinking':
      return <Brain className={cls} />;
    case 'file_read':
      return <FileText className={cls} />;
    case 'file_write':
      return <FilePlus2 className={cls} />;
    case 'file_edit':
      return <FileDiff className={cls} />;
    case 'command':
      return <Terminal className={cls} />;
    case 'web_search':
      return <Search className={cls} />;
    case 'web_fetch':
      return <Globe className={cls} />;
    case 'tool_call':
    case 'tool_result':
      return <Wrench className={cls} />;
    default:
      return <Code2 className={cls} />;
  }
}

function compactJson(value: unknown) {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function StepRow({ step }: { step: ExecutionStep }) {
  const [open, setOpen] = useState(step.status === 'running' || step.defaultCollapsed === false);
  const hasDetails = Boolean(step.content || step.inputPreview || step.outputPreview || step.error || step.metadata);
  const duration = formatDuration(step.durationMs);
  const tone =
    step.status === 'failed'
      ? 'border-error/30 bg-error/10 text-error'
      : step.status === 'running'
        ? 'border-warning/30 bg-warning/10 text-warning'
        : 'border-success/25 bg-success/10 text-success';

  return (
    <div className={cn('rounded-lg border transition-colors', tone)}>
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
        onClick={() => hasDetails && setOpen((value) => !value)}
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-black/15">
          {stepIcon(step)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">
            <SmoothStreamingText text={step.title} active={step.status === 'running'} />
          </span>
          {(step.subtitle || duration) && (
            <span className="block truncate text-xs opacity-75">
              {step.subtitle}
              {step.subtitle && duration ? ' · ' : ''}
              {duration}
            </span>
          )}
        </span>
        {hasDetails && (open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />)}
      </button>

      {open && hasDetails && (
        <div className="space-y-2 border-t border-current/15 px-3 py-2 text-xs text-foreground">
          {step.content && (
            <div className="rounded-md bg-background/70 p-2 leading-relaxed text-foreground-muted">
              <SmoothStreamingText text={step.content} active={step.status === 'running'} chunkSize={5} />
            </div>
          )}
          {step.inputPreview && (
            <pre className="max-h-48 overflow-auto rounded-md bg-[#090909] p-2 font-mono text-[11px] text-foreground-muted">
              {step.inputPreview}
            </pre>
          )}
          {step.outputPreview && (
            <pre className="max-h-64 overflow-auto rounded-md bg-[#090909] p-2 font-mono text-[11px] text-success">
              {step.outputPreview}
            </pre>
          )}
          {step.error && (
            <pre className="max-h-64 overflow-auto rounded-md bg-error/10 p-2 font-mono text-[11px] text-error">
              {step.error}
            </pre>
          )}
          {step.metadata && (
            <pre className="max-h-40 overflow-auto rounded-md bg-[#090909] p-2 font-mono text-[11px] text-foreground-subtle">
              {compactJson(step.metadata)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export function ExecutionSegmentCard({ segment }: ExecutionSegmentCardProps) {
  const [open, setOpen] = useState(segment.status === 'running' || segment.defaultCollapsed === false);
  const duration = formatDuration(segment.durationMs);
  const status = statusLabel[segment.status] ?? segment.status;
  const stats = useMemo(
    () =>
      [
        segment.toolCallCount ? `${segment.toolCallCount} tools` : '',
        segment.commandCount ? `${segment.commandCount} commands` : '',
        segment.fileReadCount + segment.fileWriteCount + segment.fileEditCount
          ? `${segment.fileReadCount + segment.fileWriteCount + segment.fileEditCount} files`
          : '',
        segment.webRequestCount ? `${segment.webRequestCount} web` : '',
        segment.totalTokens ? `${segment.totalTokens} tokens` : '',
      ].filter(Boolean),
    [segment],
  );
  const tone =
    segment.status === 'failed'
      ? 'border-error/30 bg-error/5'
      : segment.status === 'running'
        ? 'border-primary/35 bg-primary/5'
        : 'border-border bg-surface';

  return (
    <div className={cn('overflow-hidden rounded-xl border transition-all', tone)}>
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/15 text-primary">
          {segment.status === 'running' ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : segment.status === 'failed' ? (
            <AlertTriangle className="h-4 w-4 text-error" />
          ) : (
            <CheckCircle2 className="h-4 w-4 text-success" />
          )}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-foreground">
            <SmoothStreamingText text={segment.title || '处理区间'} active={segment.status === 'running'} />
          </span>
          <span className="block truncate text-xs text-foreground-subtle">
            {status}
            {duration ? ` · ${duration}` : ''}
            {stats.length ? ` · ${stats.join(' · ')}` : ''}
          </span>
        </span>
        {open ? <ChevronDown className="h-4 w-4 text-foreground-muted" /> : <ChevronRight className="h-4 w-4 text-foreground-muted" />}
      </button>

      {open && (
        <div className="space-y-2 border-t border-border/70 px-3 py-3">
          {segment.goal && (
            <div className="rounded-lg bg-background/70 px-3 py-2 text-xs leading-relaxed text-foreground-muted">
              <SmoothStreamingText text={segment.goal} active={segment.status === 'running'} />
            </div>
          )}
          {segment.errors?.map((error) => (
            <div key={error.id} className="rounded-lg border border-error/30 bg-error/10 px-3 py-2 text-xs text-error">
              <div className="font-medium">{error.title}</div>
              <div className="mt-1 text-error/90">{error.message}</div>
            </div>
          ))}
          <div className="space-y-2">
            {segment.steps.map((step) => (
              <StepRow key={step.id} step={step} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
