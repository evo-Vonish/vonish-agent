import { AlertTriangle, Copy, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { WorkflowError } from '@/types';
import { useChatStore } from '@/stores/chatStore';

interface WorkflowErrorCardProps {
  error: WorkflowError;
  retryPrompt?: string;
  className?: string;
}

const defaultContinuePrompt =
  '继续任务。请基于上一次工作流中断的位置继续执行，先简要说明中断原因和恢复计划，然后继续完成任务。';

function severityLabel(severity: WorkflowError['severity']) {
  if (severity === 'fatal') return '严重错误';
  if (severity === 'warning') return '工作流警告';
  if (severity === 'info') return '系统提示';
  return '工作流已中断';
}

export function WorkflowErrorCard({ error, retryPrompt, className }: WorkflowErrorCardProps) {
  const sendMessage = useChatStore((state) => state.sendMessage);
  const isStreaming = useChatStore((state) => state.isStreaming);
  const detail = [
    error.errorType ? `类型: ${error.errorType}` : '',
    error.stepId ? `步骤: ${error.stepId}` : '',
    error.detailsRef ? `详情: ${error.detailsRef}` : '',
  ].filter(Boolean);

  const continueTask = () => {
    if (isStreaming) return;
    void sendMessage(retryPrompt || defaultContinuePrompt);
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
    <div
      className={cn(
        'codex-panel-reveal w-full rounded-[14px] border border-error/25 bg-error/10 px-4 py-3 text-error shadow-sm',
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-error/30 bg-background text-error">
          <AlertTriangle className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{severityLabel(error.severity)}</div>
          <div className="mt-1 text-[15px] font-medium leading-6 text-foreground">{error.title}</div>
          <div className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-error/90">
            {error.message}
          </div>
          {detail.length > 0 && (
            <div className="mt-2 space-y-1 rounded-[10px] bg-black/20 px-3 py-2 font-mono text-xs leading-5 text-error/80">
              {detail.map((line) => (
                <div key={line}>{line}</div>
              ))}
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={continueTask}
              disabled={isStreaming}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors',
                isStreaming
                  ? 'cursor-not-allowed bg-white/5 text-foreground-subtle'
                  : 'bg-error/20 text-error hover:bg-error/30',
              )}
            >
              <RotateCcw className="h-3.5 w-3.5" />
              继续任务
            </button>
            <button
              type="button"
              onClick={copyError}
              className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-error/80 transition-colors hover:bg-error/20 hover:text-error"
            >
              <Copy className="h-3.5 w-3.5" />
              复制错误
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
