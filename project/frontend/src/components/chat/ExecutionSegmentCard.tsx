import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  FileDiff,
  FilePlus2,
  FileText,
  Globe,
  Loader2,
  Pencil,
  Search,
  TerminalSquare,
  Wrench,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ExecutionSegment, ExecutionStep } from '@/types';
import { SmoothStreamingText } from './SmoothStreamingText';

interface ExecutionSegmentCardProps {
  segment: ExecutionSegment;
}

type StepKind = 'thinking' | 'command' | 'file' | 'web' | 'tool' | 'error';

const stepLabels: Record<StepKind, { done: string; running: string; failed: string; panel: string }> = {
  thinking: { done: '已完成思考', running: '正在思考', failed: '思考中断', panel: 'Thinking' },
  command: { done: '已运行命令', running: '正在运行命令', failed: '命令失败', panel: 'Shell' },
  file: { done: '已编辑文件', running: '正在编辑文件', failed: '文件操作失败', panel: 'File' },
  web: { done: '已检索网页', running: '正在检索网页', failed: '网页检索失败', panel: 'Web' },
  tool: { done: '已调用工具', running: '正在调用工具', failed: '工具调用失败', panel: 'Tool' },
  error: { done: '工作流提示', running: '工作流提示', failed: '工作流已中断', panel: 'Error' },
};

function formatDuration(ms?: number) {
  if (!ms || ms < 0) return '';
  if (ms < 1000) return `${Math.max(1, Math.round(ms))}ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`;
}

function stepKind(step: ExecutionStep): StepKind {
  if (step.type === 'thinking') return 'thinking';
  if (step.type === 'command') return 'command';
  if (step.type === 'file_read' || step.type === 'file_write' || step.type === 'file_edit') return 'file';
  if (step.type === 'web_search' || step.type === 'web_fetch') return 'web';
  if (step.type === 'error_notice') return 'error';
  return 'tool';
}

function StepIcon({ step }: { step: ExecutionStep }) {
  const cls = 'h-4 w-4';
  if (step.status === 'running') return <Loader2 className={cn(cls, 'animate-spin')} />;
  if (step.status === 'failed') return <AlertTriangle className={cls} />;
  switch (stepKind(step)) {
    case 'thinking':
      return <Brain className={cls} />;
    case 'command':
      return <TerminalSquare className={cls} />;
    case 'file':
      if (step.type === 'file_read') return <FileText className={cls} />;
      if (step.type === 'file_write') return <FilePlus2 className={cls} />;
      return <FileDiff className={cls} />;
    case 'web':
      return step.type === 'web_search' ? <Search className={cls} /> : <Globe className={cls} />;
    case 'error':
      return <AlertTriangle className={cls} />;
    default:
      return <Wrench className={cls} />;
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

function parsePreviewJson(value?: string): Record<string, unknown> | null {
  if (!value) return null;
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function commandLine(step: ExecutionStep) {
  const args = parsePreviewJson(step.inputPreview);
  return String(args?.command ?? args?.code ?? step.subtitle ?? step.inputPreview ?? step.title);
}

function primarySubject(step: ExecutionStep) {
  const args = parsePreviewJson(step.inputPreview);
  return String(
    args?.path ??
      args?.file_path ??
      args?.url ??
      args?.query ??
      args?.queries ??
      step.subtitle ??
      step.toolName ??
      '',
  );
}

function stepHeading(step: ExecutionStep) {
  const labels = stepLabels[stepKind(step)];
  if (step.status === 'running') return labels.running;
  if (step.status === 'failed') return labels.failed;
  return labels.done;
}

function statusText(step: ExecutionStep) {
  if (step.status === 'running') return '执行中';
  if (step.status === 'failed') return '失败';
  if (step.status === 'cancelled') return '已取消';
  const duration = formatDuration(step.durationMs);
  return duration ? `成功 ${duration}` : '成功';
}

function CodePanel({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'error' }) {
  return (
    <div
      className={cn(
        'codex-panel-reveal relative overflow-hidden rounded-[10px] bg-[#252525] text-[13px] shadow-sm',
        tone === 'error' && 'bg-error/10',
      )}
    >
      {children}
    </div>
  );
}

function TimelineShell({
  children,
  icon,
  last = false,
  tone = 'neutral',
}: {
  children: React.ReactNode;
  icon: React.ReactNode;
  last?: boolean;
  tone?: 'neutral' | 'running' | 'error';
}) {
  return (
    <div className="relative pl-9">
      {!last && (
        <span
          className={cn(
            'absolute left-[9px] top-7 bottom-[-18px] w-px bg-white/14',
            tone === 'error' && 'bg-error/30',
            tone === 'running' && 'bg-primary/35',
          )}
        />
      )}
      <span
        className={cn(
          'absolute left-0 top-0 z-10 flex h-5 w-5 items-center justify-center rounded-full border border-white/12 bg-background text-foreground-muted shadow-[0_0_0_4px_hsl(var(--background))]',
          tone === 'error' && 'border-error/35 bg-error/10 text-error',
          tone === 'running' && 'border-primary/35 bg-primary/10 text-primary',
        )}
      >
        {icon}
      </span>
      {children}
    </div>
  );
}

function StepDetails({ step }: { step: ExecutionStep }) {
  const kind = stepKind(step);
  const label = stepLabels[kind].panel;
  const subject = primarySubject(step);
  const showCommand = kind === 'command';
  const output = step.error || step.outputPreview || step.content || '';
  const metadata = step.metadata ? compactJson(step.metadata) : '';

  return (
    <CodePanel tone={step.status === 'failed' ? 'error' : 'neutral'}>
      <div className="border-b border-white/5 px-3 py-2 text-sm text-foreground-muted">
        {label}
      </div>
      <div className="max-h-[360px] overflow-auto px-3 py-3 font-mono text-sm leading-6 text-foreground">
        {showCommand ? (
          <div className="whitespace-pre-wrap">
            <span className="text-foreground-subtle">$ </span>
            <SmoothStreamingText text={commandLine(step)} active={step.status === 'running'} chunkSize={5} />
          </div>
        ) : (
          subject && <div className="mb-2 break-words text-foreground">{subject}</div>
        )}
        {step.inputPreview && !showCommand && (
          <pre className="whitespace-pre-wrap break-words text-foreground-muted">{step.inputPreview}</pre>
        )}
        {output && (
          <pre
            className={cn(
              'mt-3 whitespace-pre-wrap break-words text-foreground-muted',
              step.status === 'failed' && 'text-error',
            )}
          >
            <SmoothStreamingText text={output} active={step.status === 'running'} chunkSize={5} />
          </pre>
        )}
        {metadata && (
          <pre className="mt-3 whitespace-pre-wrap break-words text-foreground-subtle">{metadata}</pre>
        )}
        {!showCommand && !subject && !step.inputPreview && !output && !metadata && (
          <span className="text-foreground-subtle">无输出</span>
        )}
      </div>
      <div
        className={cn(
          'flex items-center justify-end gap-2 px-3 pb-2 text-sm',
          step.status === 'failed' ? 'text-error' : 'text-foreground-muted',
        )}
      >
        {step.status === 'running' ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : step.status === 'failed' ? (
          <AlertTriangle className="h-3.5 w-3.5" />
        ) : (
          <Check className="h-3.5 w-3.5" />
        )}
        <span>{statusText(step)}</span>
      </div>
    </CodePanel>
  );
}

function StepBlock({ step, last = false }: { step: ExecutionStep; last?: boolean }) {
  const hasDetails = Boolean(step.content || step.inputPreview || step.outputPreview || step.error || step.metadata || step.subtitle);
  const [open, setOpen] = useState(step.status === 'running' || step.defaultCollapsed === false);
  const subject = primarySubject(step);
  const tone = step.status === 'failed' ? 'error' : step.status === 'running' ? 'running' : 'neutral';

  return (
    <TimelineShell icon={<StepIcon step={step} />} last={last} tone={tone}>
      <div className="space-y-2 pb-1">
        <button
          type="button"
          className={cn(
            'group flex max-w-full items-center gap-2 text-left text-[15px] font-medium transition-colors duration-200',
            step.status === 'failed' ? 'text-error' : 'text-foreground-muted hover:text-foreground',
          )}
          onClick={() => hasDetails && setOpen((value) => !value)}
        >
          <span className="min-w-0 truncate">
            <SmoothStreamingText text={stepHeading(step)} active={step.status === 'running'} />
            {subject ? <span className="ml-1 text-foreground-subtle">{subject}</span> : null}
          </span>
          {hasDetails && (
            <span className="rounded-md p-0.5 text-foreground-subtle transition-colors group-hover:bg-white/5 group-hover:text-foreground">
              {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
            </span>
          )}
        </button>
        {open && hasDetails && <StepDetails step={step} />}
      </div>
    </TimelineShell>
  );
}

function SegmentSummary({ segment }: { segment: ExecutionSegment }) {
  const edited = segment.fileWriteCount + segment.fileEditCount;
  const commands = segment.commandCount;
  const tools = Math.max(0, segment.toolCallCount - commands);
  const parts = [
    edited ? `已编辑 ${edited} 个文件` : '',
    commands ? `已运行 ${commands} 条命令` : '',
    tools ? `已调用 ${tools} 个工具` : '',
    segment.webRequestCount ? `已检索 ${segment.webRequestCount} 次网页` : '',
  ].filter(Boolean);

  if (parts.length) return <>{parts.join(' ')}</>;
  if (segment.status === 'running') return <>正在处理</>;
  if (segment.status === 'failed') return <>工作流已中断</>;
  return <>已处理完成</>;
}

export function ExecutionSegmentCard({ segment }: ExecutionSegmentCardProps) {
  const [open, setOpen] = useState(segment.status === 'running' || segment.defaultCollapsed === false);
  const duration = formatDuration(segment.durationMs);
  const stats = useMemo(
    () =>
      [
        segment.totalTokens ? `${segment.totalTokens} tokens` : '',
        duration ? `耗时 ${duration}` : '',
      ].filter(Boolean),
    [duration, segment.totalTokens],
  );

  return (
    <div className="space-y-4">
      <TimelineShell
        icon={
          segment.status === 'running' ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : segment.status === 'failed' ? (
            <AlertTriangle className="h-4 w-4" />
          ) : (
            <Pencil className="h-4 w-4" />
          )
        }
        last={!open || (segment.steps.length === 0 && !segment.goal && !segment.errors?.length)}
        tone={segment.status === 'failed' ? 'error' : segment.status === 'running' ? 'running' : 'neutral'}
      >
        <button
          type="button"
          className="group flex max-w-full items-center gap-2 text-left text-[15px] font-semibold text-foreground-muted transition-colors duration-200 hover:text-foreground"
          onClick={() => setOpen((value) => !value)}
        >
          <span className="min-w-0 truncate">
            <SegmentSummary segment={segment} />
            {stats.length ? <span className="ml-2 font-normal text-foreground-subtle">{stats.join(' · ')}</span> : null}
          </span>
          <span className="rounded-md p-0.5 text-foreground-subtle transition-colors group-hover:bg-white/5 group-hover:text-foreground">
            {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          </span>
        </button>
      </TimelineShell>

      {open && (
        <div className="space-y-4">
          {segment.goal && (
            <TimelineShell icon={<span className="h-1.5 w-1.5 rounded-full bg-current" />} last={segment.steps.length === 0 && !segment.errors?.length}>
              <div className="text-[15px] leading-7 text-foreground">
                <SmoothStreamingText text={segment.goal} active={segment.status === 'running'} />
              </div>
            </TimelineShell>
          )}
          {segment.errors?.map((error, index) => (
            <TimelineShell
              key={error.id}
              icon={<AlertTriangle className="h-4 w-4" />}
              tone="error"
              last={segment.steps.length === 0 && index === (segment.errors?.length ?? 0) - 1}
            >
              <div className="codex-panel-reveal rounded-[10px] bg-error/10 px-3 py-2 text-sm text-error">
                <div className="font-medium">{error.title}</div>
                <div className="mt-1 text-error/90">{error.message}</div>
              </div>
            </TimelineShell>
          ))}
          {segment.steps.map((step, index) => (
            <StepBlock key={step.id} step={step} last={index === segment.steps.length - 1} />
          ))}
          {segment.status !== 'running' && segment.steps.length > 1 && (
            <div className="pl-9">
              <button
                type="button"
                className="flex items-center gap-2 rounded-md px-1 py-0.5 text-[15px] text-foreground-subtle transition-colors duration-200 hover:bg-white/5 hover:text-foreground"
                onClick={() => setOpen(false)}
              >
                <ChevronDown className="h-4 w-4" />
                收起本次处理
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
