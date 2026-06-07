import { useMemo } from 'react';
import {
  AlertTriangle,
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  FileDiff,
  FilePlus2,
  FileText,
  Globe,
  Loader2,
  MessageSquareQuote,
  Pencil,
  Search,
  Sparkles,
  TerminalSquare,
  Wrench,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ExecutionSegment, ExecutionStep } from '@/types';
import { useInlinePromptStore } from '@/stores/inlinePromptStore';
import { useReferenceStore, type NewReference } from '@/stores/referenceStore';
import { SmoothStreamingText } from './SmoothStreamingText';
import { ExecutionCollapse } from './ExecutionCollapse';
import { useExecutionDisclosure } from './useExecutionDisclosure';

interface ExecutionSegmentCardProps {
  segment: ExecutionSegment;
}

type StepKind = 'thinking' | 'command' | 'file' | 'web' | 'research' | 'tool' | 'error';

const stepLabels: Record<StepKind, { done: string; running: string; failed: string; panel: string }> = {
  thinking: { done: '已完成思考', running: '正在思考', failed: '思考中断', panel: 'Thinking' },
  command: { done: '已运行命令', running: '正在运行命令', failed: '命令失败', panel: 'Shell' },
  file: { done: '已编辑文件', running: '正在编辑文件', failed: '文件操作失败', panel: 'File' },
  web: { done: '已检索网页', running: '正在检索网页', failed: '网页检索失败', panel: 'Web' },
  research: { done: '已完成研究', running: '正在研究', failed: '研究失败', panel: 'Research' },
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
  if (step.type === 'research') return 'research';
  if (step.type === 'error_notice') return 'error';
  return 'tool';
}

function StepIcon({ step }: { step: ExecutionStep }) {
  const cls = 'h-4 w-4';
  if (step.status === 'running' || step.status === 'retrying') return <Loader2 className={cn(cls, 'animate-spin')} />;
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
    case 'research':
      return <Globe className={cls} />;
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
  if (step.status === 'running' || step.status === 'retrying') return labels.running;
  if (step.status === 'failed') return labels.failed;
  return labels.done;
}

function statusText(step: ExecutionStep) {
  if (step.status === 'running') return '执行中';
  if (step.status === 'retrying') return '重试中';
  if (step.status === 'failed') return '失败';
  if (step.status === 'cancelled') return '已取消';
  if (step.status === 'skipped') return '已跳过';
  const duration = formatDuration(step.durationMs);
  return duration ? `成功 ${duration}` : '成功';
}

function CodePanel({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'error' }) {
  return (
    <div
      className={cn(
        'codex-panel-reveal codex-detail-panel relative overflow-hidden rounded-[10px] bg-[#252525] text-[13px] shadow-sm',
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
            'workflow-rail-line',
            tone === 'error' && 'workflow-rail-line-error',
            tone === 'running' && 'workflow-rail-line-running',
          )}
        />
      )}
      <span
        className={cn(
          'workflow-rail-icon',
          tone === 'error' && 'workflow-rail-icon-error',
          tone === 'running' && 'workflow-rail-icon-running',
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
  const output = kind === 'thinking'
    ? (step.error || step.content || step.outputPreview || '')
    : (step.error || step.outputPreview || step.content || '');
  const toolResult = step.metadata?.result;
  const metadata = step.metadata
    ? compactJson({ ...step.metadata, result: undefined })
    : '';
  const gitToolName = String(step.metadata?.toolName ?? step.toolName ?? '');

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
        {gitToolName.startsWith('git_') && toolResult !== undefined && toolResult !== null && (
          <GitToolResultView toolName={gitToolName} result={toolResult} />
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
        {step.status === 'running' || step.status === 'retrying' ? (
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

function GitToolResultView({ toolName, result }: { toolName: string; result: unknown }) {
  if (!result || typeof result !== 'object') return null;
  const data = result as Record<string, any>;
  if (data.is_git_repo === false) {
    return <div className="mt-3 rounded-md bg-white/[0.04] px-3 py-2 text-foreground-muted">当前 Workspace 不是 Git 仓库。</div>;
  }
  if (toolName === 'git_status') {
    const rows = ['staged', 'modified', 'untracked', 'deleted', 'conflicts']
      .flatMap((key) => (data[key] ?? []).map((path: string) => ({ key, path })));
    return (
      <div className="mt-3 space-y-2 rounded-md bg-white/[0.04] px-3 py-2 font-sans text-xs">
        <div className="text-foreground">{data.branch || 'HEAD'} · {rows.length ? `${rows.length} changed` : 'Clean'}</div>
        {rows.slice(0, 20).map((row) => (
          <div key={`${row.key}-${row.path}`} className="flex gap-2 text-foreground-muted">
            <span className="w-16 text-foreground-subtle">{row.key}</span>
            <span className="min-w-0 truncate">{row.path}</span>
          </div>
        ))}
      </div>
    );
  }
  if (toolName === 'git_diff') {
    const files = (data.files ?? []) as Array<{ path: string; additions: number; deletions: number; patch: string }>;
    return (
      <div className="mt-3 space-y-2 font-sans text-xs">
        <div className="text-foreground-muted">
          {files.length} files changed · <span className="text-success">+{data.additions ?? 0}</span>{' '}
          <span className="text-error">-{data.deletions ?? 0}</span>
        </div>
        {files.slice(0, 5).map((file) => (
          <details key={file.path} className="rounded-md bg-white/[0.04]" open={files.length === 1}>
            <summary className="cursor-pointer px-3 py-2 text-foreground">
              {file.path} <span className="text-success">+{file.additions}</span> <span className="text-error">-{file.deletions}</span>
            </summary>
            <pre className="max-h-56 overflow-auto border-t border-white/5 px-3 py-2 font-mono text-[11px] text-foreground-muted">{file.patch}</pre>
          </details>
        ))}
      </div>
    );
  }
  if (toolName === 'git_history') {
    return (
      <div className="mt-3 space-y-2 font-sans text-xs">
        {(data.commits ?? []).slice(0, 10).map((commit: any) => (
          <div key={commit.hash} className="rounded-md bg-white/[0.04] px-3 py-2">
            <div className="truncate text-foreground">{commit.message}</div>
            <div className="mt-1 flex gap-2 text-foreground-subtle">
              <span className="font-mono">{commit.short_hash}</span>
              <span>{commit.author}</span>
              <span>{commit.date}</span>
            </div>
          </div>
        ))}
      </div>
    );
  }
  return null;
}

function StepBlock({ step, last = false }: { step: ExecutionStep; last?: boolean }) {
  const kind = stepKind(step);
  const outputText = String(step.outputPreview || step.content || '').trim();
  const hasThinkingContent = kind === 'thinking' && Boolean(String(step.content || '').trim());
  const isGenericCompletedThinking =
    kind === 'thinking' &&
    !hasThinkingContent &&
    step.status !== 'running' &&
    step.status !== 'retrying' &&
    !step.error &&
    !step.inputPreview &&
    !step.metadata &&
    (!outputText || outputText === '思考完成');
  const hasDetails = !isGenericCompletedThinking && Boolean(step.content || step.inputPreview || step.outputPreview || step.error || step.metadata || step.subtitle);
  const disclosure = useExecutionDisclosure({
    id: step.id,
    status: step.status,
    defaultCollapsed: step.defaultCollapsed,
    defaultExpanded: step.defaultCollapsed === false,
    failedStatuses: ['failed'],
    interruptedStatuses: ['cancelled'],
    terminalStatuses: ['completed', 'failed', 'cancelled', 'skipped'],
  });
  const open = disclosure.expanded;
  const subject = primarySubject(step);
  const tone = step.status === 'failed' ? 'error' : step.status === 'running' || step.status === 'retrying' ? 'running' : 'neutral';
  const addReference = useReferenceStore((state) => state.addReference);
  const openPrompt = useInlinePromptStore((state) => state.openPrompt);
  const fullText = [
    step.title,
    subject,
    step.inputPreview,
    step.content,
    step.outputPreview,
    step.error,
    step.metadata ? compactJson(step.metadata) : '',
  ].filter(Boolean).join('\n\n');
  const draft: NewReference = {
    sourceType: stepKind(step) === 'thinking' ? 'chat' : 'artifact-block',
    sourceId: step.id,
    title: `${stepHeading(step)}${subject ? ` · ${subject}` : ''}`,
    preview: fullText.slice(0, 4000),
    location: {
      blockId: step.id,
      blockType: step.type,
    },
    payload: {
      step,
    },
  };

  return (
    <TimelineShell icon={<StepIcon step={step} />} last={last} tone={tone}>
      <div className="space-y-1.5 pb-0.5">
        <div className="group flex max-w-full items-center gap-2">
          <button
            type="button"
            className={cn(
              'flex min-w-0 items-center gap-2 text-left text-[14px] font-medium transition-colors duration-200',
              step.status === 'failed' ? 'text-error' : 'text-foreground-muted hover:text-foreground',
            )}
            onClick={() => hasDetails && disclosure.toggle()}
          >
            <span
              className="execution-title min-w-0 truncate"
              data-motion={disclosure.titleMotion}
              data-tone={disclosure.tone}
              data-kind={kind}
            >
              <SmoothStreamingText text={stepHeading(step)} active={step.status === 'running' || step.status === 'retrying'} />
              {subject ? <span className="ml-1 text-foreground-subtle">{subject}</span> : null}
            </span>
            {hasDetails && (
              <span className="rounded-md p-0.5 text-foreground-subtle transition-colors group-hover:bg-white/5 group-hover:text-foreground">
                {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
              </span>
            )}
          </button>
          {hasDetails && (
            <span className="ml-1 flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100" data-quote-card="execution-step">
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  addReference(draft);
                }}
                className="rounded p-0.5 text-foreground-subtle hover:bg-white/5 hover:text-foreground"
                title="引用完整步骤"
              >
                <MessageSquareQuote className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  openPrompt(draft, { left: Math.max(16, window.innerWidth / 2 - 170), top: Math.max(16, window.innerHeight - 250) });
                }}
                className="rounded p-0.5 text-foreground-subtle hover:bg-white/5 hover:text-[#e0a072]"
                title="询问 AI"
              >
                <Sparkles className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  void navigator.clipboard?.writeText(fullText).catch(() => {});
                }}
                className="rounded p-0.5 text-foreground-subtle hover:bg-white/5 hover:text-foreground"
                title="复制完整步骤"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
            </span>
          )}
        </div>
        {hasDetails && (
          <ExecutionCollapse open={open}>
            <StepDetails step={step} />
          </ExecutionCollapse>
        )}
      </div>
    </TimelineShell>
  );
}

function isNoisyResearchFailure(step: ExecutionStep) {
  const toolName = String(step.toolName || step.metadata?.toolName || '');
  return (
    step.status === 'failed' &&
    (step.type === 'research' ||
      step.type === 'web_fetch' ||
      step.type === 'web_search' ||
      toolName === 'deep_research' ||
      toolName === 'research_fetch' ||
      toolName === 'research_search' ||
      toolName === 'web_fetch')
  );
}

function failureLabel(step: ExecutionStep) {
  return String(step.toolName || step.metadata?.toolName || step.type || 'research');
}

function failureMessage(step: ExecutionStep) {
  return String(step.error || step.outputPreview || '抓取或正文提取失败');
}

function ResearchFailureAggregate({ steps, last = false }: { steps: ExecutionStep[]; last?: boolean }) {
  const disclosure = useExecutionDisclosure({
    id: `research-failures-${steps.map((step) => step.id).join('-')}`,
    status: 'completed',
    defaultCollapsed: true,
    terminalStatuses: ['completed'],
  });
  const byTool = steps.reduce<Record<string, number>>((acc, step) => {
    const key = failureLabel(step);
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const retryable = steps.filter((step) => /retry|timeout|http|extract|text/i.test(failureMessage(step))).length;

  return (
    <TimelineShell icon={<AlertTriangle className="h-4 w-4" />} last={last} tone="neutral">
      <div className="space-y-1.5 pb-0.5">
        <button
          type="button"
          className="group flex max-w-full items-center gap-2 text-left text-[14px] font-medium text-[#b8933e] transition-colors duration-200 hover:text-[#d3b66e]"
          onClick={() => disclosure.toggle()}
        >
          <span className="execution-title min-w-0 truncate" data-motion={disclosure.titleMotion} data-tone="neutral" data-kind="research">
            抓取网页完成
            <span className="ml-1 text-foreground-subtle">
              失败 {steps.length} · 可重试 {retryable}
            </span>
          </span>
          <span className="rounded-md p-0.5 text-foreground-subtle transition-colors group-hover:bg-white/5 group-hover:text-foreground">
            {disclosure.expanded ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          </span>
        </button>
        <ExecutionCollapse open={disclosure.expanded}>
          <CodePanel tone="neutral">
            <div className="border-b border-white/5 px-3 py-2 text-sm text-foreground-muted">
              Research failures were grouped to avoid retry noise.
            </div>
            <div className="max-h-[320px] overflow-auto px-3 py-3 text-sm leading-6">
              <div className="mb-3 flex flex-wrap gap-1.5">
                {Object.entries(byTool).map(([name, count]) => (
                  <span key={name} className="rounded-md bg-white/[0.045] px-2 py-1 font-mono-code text-[11px] text-[#9a9590]">
                    {name} × {count}
                  </span>
                ))}
              </div>
              <div className="space-y-2">
                {steps.map((step, index) => (
                  <div key={step.id} className="rounded-md bg-black/20 px-2.5 py-2">
                    <div className="flex gap-2 text-xs text-[#9a9590]">
                      <span className="w-7 shrink-0 font-mono-code text-[#5c5855]">#{index + 1}</span>
                      <span className="min-w-0 truncate font-mono-code">{failureLabel(step)}</span>
                    </div>
                    {primarySubject(step) && (
                      <div className="mt-1 break-words text-xs text-foreground-muted">{primarySubject(step)}</div>
                    )}
                    <div className="mt-1 whitespace-pre-wrap break-words text-xs text-[#c97a76]">{failureMessage(step)}</div>
                  </div>
                ))}
              </div>
            </div>
          </CodePanel>
        </ExecutionCollapse>
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
  const disclosure = useExecutionDisclosure({
    id: segment.id,
    status: segment.status,
    defaultCollapsed: segment.defaultCollapsed,
    defaultExpanded: segment.defaultCollapsed === false,
    failedStatuses: ['failed'],
    interruptedStatuses: ['cancelled'],
    terminalStatuses: ['completed', 'failed', 'cancelled'],
  });
  const open = disclosure.expanded;
  const duration = formatDuration(segment.durationMs);
  const stats = useMemo(
    () =>
      [
        segment.totalTokens ? `${segment.totalTokens} tokens` : '',
        duration ? `耗时 ${duration}` : '',
      ].filter(Boolean),
    [duration, segment.totalTokens],
  );
  const noisyFailures = useMemo(
    () => segment.steps.filter(isNoisyResearchFailure),
    [segment.steps],
  );
  const visibleSteps = useMemo(
    () => segment.steps.filter((step) => !isNoisyResearchFailure(step)),
    [segment.steps],
  );

  return (
    <div className="space-y-2.5">
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
          onClick={() => disclosure.toggle()}
        >
          <span
            className="execution-title min-w-0 truncate"
            data-motion={disclosure.titleMotion}
            data-tone={disclosure.tone}
            data-kind="segment"
          >
            <SegmentSummary segment={segment} />
            {stats.length ? <span className="ml-2 font-normal text-foreground-subtle">{stats.join(' · ')}</span> : null}
          </span>
          <span className="rounded-md p-0.5 text-foreground-subtle transition-colors group-hover:bg-white/5 group-hover:text-foreground">
            {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          </span>
        </button>
      </TimelineShell>

      <ExecutionCollapse open={open}>
        <div className="space-y-2.5">
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
          {noisyFailures.length > 0 && (
            <ResearchFailureAggregate steps={noisyFailures} last={visibleSteps.length === 0} />
          )}
          {visibleSteps.map((step, index) => (
            <StepBlock key={step.id} step={step} last={index === visibleSteps.length - 1} />
          ))}
          {segment.status !== 'running' && segment.steps.length > 1 && (
            <div className="pl-9">
              <button
                type="button"
                className="flex items-center gap-2 rounded-md px-1 py-0.5 text-[15px] text-foreground-subtle transition-colors duration-200 hover:bg-white/5 hover:text-foreground"
                onClick={() => disclosure.setExpanded(false)}
              >
                <ChevronDown className="h-4 w-4" />
                收起本次处理
              </button>
            </div>
          )}
        </div>
      </ExecutionCollapse>
    </div>
  );
}
