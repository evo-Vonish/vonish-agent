import { AlertTriangle, ChevronDown, ChevronRight, Copy, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { WorkflowError } from '@/types';
import { useChatStore } from '@/stores/chatStore';
import { ExecutionCollapse } from './ExecutionCollapse';
import { useExecutionDisclosure } from './useExecutionDisclosure';

interface WorkflowErrorCardProps {
  error: WorkflowError;
  retryPrompt?: string;
  className?: string;
}

const defaultContinuePrompt =
  '继续执行当前任务，从上一次未完成的位置恢复。不要要求用户重复需求，不要重复已经完成的工作，直接继续完成任务。';

function severityLabel(severity: WorkflowError['severity']) {
  if (severity === 'fatal') return '严重错误';
  if (severity === 'warning') return '工作流警告';
  if (severity === 'info') return '系统提示';
  return '工作流已中断';
}

export function WorkflowErrorCard({ error, retryPrompt, className }: WorkflowErrorCardProps) {
  const resumeWorkflow = useChatStore((state) => state.resumeWorkflow);
  const isStreaming = useChatStore((state) => state.isStreaming);
  const disclosure = useExecutionDisclosure({
    id: error.id,
    status: 'error',
    defaultCollapsed: true,
    failedStatuses: ['error'],
    terminalStatuses: ['error'],
  });
  const expanded = disclosure.expanded;
  const detail = [
    error.errorType ? `类型: ${error.errorType}` : '',
    error.stepId ? `步骤: ${error.stepId}` : '',
    error.detailsRef ? `详情: ${error.detailsRef}` : '',
  ].filter(Boolean);

  const continueTask = () => {
    if (isStreaming) return;
    void resumeWorkflow(retryPrompt || defaultContinuePrompt);
  };

  const copyError = () => {
    const text = [
      `${severityLabel(error.severity)}: ${error.title}`,
      error.message,
      ...detail,
    ].join('\n');
    void navigator.clipboard?.writeText(text).catch(() => {});
  };

  return (
    <div className={cn('relative space-y-1.5 pl-9 text-error', className)}>
      {expanded && <span className="workflow-rail-line workflow-rail-line-short workflow-rail-line-error" />}
      <span className="workflow-rail-icon workflow-rail-icon-error">
        <AlertTriangle className="h-4 w-4 text-error" />
      </span>
      <button
        type="button"
        onClick={() => disclosure.toggle()}
        className="flex max-w-full items-center gap-2 text-left text-[14px] font-medium text-error transition-colors hover:text-error"
      >
        <span className="execution-title min-w-0 truncate" data-motion={disclosure.titleMotion} data-tone="failed" data-kind="tool">
          {severityLabel(error.severity)}
          <span className="ml-1 text-foreground-subtle">{error.title}</span>
        </span>
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-60" />
        )}
      </button>
      <ExecutionCollapse open={expanded}>
        <div className="codex-panel-reveal codex-detail-panel relative overflow-hidden rounded-[10px] bg-[#252525] text-[13px] shadow-sm">
          <div className="border-b border-white/5 px-3 py-1.5 text-sm text-error/80">
            Workflow Error
          </div>
          <div className="max-h-[320px] space-y-2.5 overflow-auto px-3 py-2.5 font-mono text-sm leading-6">
            <pre className="whitespace-pre-wrap break-words text-error">{error.message}</pre>
            {detail.length > 0 && (
              <pre className="whitespace-pre-wrap break-words text-error/75">{detail.join('\n')}</pre>
            )}
          </div>
          <div className="flex flex-wrap justify-between gap-2 px-3 pb-2 text-sm text-error">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-3.5 w-3.5" />
              <span>{severityLabel(error.severity)}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={continueTask}
                disabled={isStreaming}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-colors',
                  isStreaming ? 'cursor-not-allowed bg-white/5 text-foreground-subtle' : 'hover:bg-error/10',
                )}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                继续任务
              </button>
              <button
                type="button"
                onClick={copyError}
                className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-error/80 transition-colors hover:bg-error/10 hover:text-error"
              >
                <Copy className="h-3.5 w-3.5" />
                复制错误
              </button>
            </div>
          </div>
        </div>
      </ExecutionCollapse>
    </div>
  );
}
