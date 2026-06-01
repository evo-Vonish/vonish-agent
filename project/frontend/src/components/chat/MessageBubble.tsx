import { Bot, FileText, Image, Sparkles, User } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatBytes } from '@/lib/utils';
import type { Message, MessageSegment, UploadedFileMeta } from '@/types';
import { useI18n } from '@/i18n';
import { useChatStore } from '@/stores/chatStore';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ThinkingCard } from './ThinkingCard';
import { ToolCard } from './ToolCard';
import { TodoCard } from './TodoCard';
import { ExecutionSegmentCard } from './ExecutionSegmentCard';
import { WorkflowErrorCard } from './WorkflowErrorCard';

interface MessageBubbleProps {
  message: Message;
  className?: string;
}

function AssistantTextBlock({ content }: { content: string }) {
  if (!content) return null;
  return (
    <div className="mb-1 w-full px-0.5 py-0.5 text-[15px] leading-7 text-foreground">
      <MarkdownRenderer content={content} />
    </div>
  );
}

function SegmentRenderer({ segment }: { segment: MessageSegment }) {
  if (segment.type === 'thinking') {
    return (
      <ThinkingCard
        id={segment.id}
        content={segment.content}
        summary={segment.summary}
        status={segment.status}
      />
    );
  }

  if (segment.type === 'tool') {
    return <ToolCard tool={segment.tool} />;
  }

  if (segment.type === 'execution') {
    return <ExecutionSegmentCard segment={segment.execution} />;
  }

  if (segment.type === 'workflow_error') {
    return <WorkflowErrorCard error={segment.error} retryPrompt={segment.retryPrompt} />;
  }

  return <AssistantTextBlock content={segment.content} />;
}

function FileIcon({ file }: { file: UploadedFileMeta }) {
  if (file.mimeType?.startsWith('image/')) return <Image className="h-3.5 w-3.5 text-primary" />;
  return <FileText className="h-3.5 w-3.5 text-foreground-subtle" />;
}

function FileCard({ file, conversationId }: { file: UploadedFileMeta; conversationId: string | null }) {
  const canOpen = Boolean(conversationId && file.workspacePath);
  const openFile = () => {
    if (!canOpen) return;
    window.open(`/api/workspaces/${conversationId}/files/${file.workspacePath}`, '_blank', 'noopener,noreferrer');
  };

  return (
    <button
      type="button"
      onClick={openFile}
      disabled={!canOpen}
      className={cn(
        'flex max-w-[220px] items-center gap-2 rounded-lg border px-2.5 py-2 text-left text-xs transition-colors',
        file.status === 'failed'
          ? 'border-error/30 bg-error/10 text-error'
          : 'border-border bg-background/80 text-foreground hover:border-primary/30 hover:bg-surface-hover',
        !canOpen && 'cursor-default',
      )}
    >
      <FileIcon file={file} />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium">{file.originalName}</span>
        <span className="block truncate text-[10px] text-foreground-subtle">
          {file.status === 'failed' ? file.error || '解析失败' : `${file.ext || 'file'} · ${formatBytes(file.size)}`}
        </span>
      </span>
    </button>
  );
}

export function MessageBubble({ message, className }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';
  const hasContent = message.content && message.content.length > 0;
  const hasSegments = Boolean(message.segments?.length);
  const { t } = useI18n();
  const conversationId = useChatStore((state) => state.currentConversationId);

  return (
    <div
      className={cn(
        'group flex gap-3 px-3 sm:px-4 py-2.5 transition-colors',
        isUser && 'flex-row-reverse',
        className,
      )}
    >
      <div
        className={cn(
          'w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5',
          isUser && 'text-foreground-subtle',
          isAssistant && 'text-success',
          message.role === 'system' && 'text-warning',
        )}
      >
        {isUser && <User className="w-3.5 h-3.5" />}
        {isAssistant && <Sparkles className="w-3.5 h-3.5" />}
        {message.role === 'system' && <Bot className="w-3.5 h-3.5" />}
      </div>

      <div className={cn('min-w-0', isUser ? 'ml-auto flex w-auto max-w-[72%] flex-col items-end' : 'flex-1')}>
        <span className="text-[10px] text-foreground-subtle mb-1.5 font-medium select-none">
          {isUser ? t('user.label') : isAssistant ? t('assistant.label') : t('system.label')}
        </span>

        {isUser && hasContent && (
          <div
            className="mb-1 max-w-full px-1 py-1 text-right text-foreground"
            style={{ maxWidth: '100%' }}
          >
            <MarkdownRenderer content={message.content} />
          </div>
        )}

        {isUser && message.files && message.files.length > 0 && (
          <div className="mb-2 flex max-w-full flex-wrap justify-end gap-2">
            {message.files.map((file) => (
              <FileCard key={file.id} file={file} conversationId={conversationId} />
            ))}
          </div>
        )}

        {!isUser && hasSegments && (
          <div className="w-full space-y-2.5">
            {message.segments?.map((segment) => (
              <SegmentRenderer key={segment.id} segment={segment} />
            ))}
          </div>
        )}

        {isAssistant && !hasSegments && (
          <>
            {((message.thinkingBlocks && message.thinkingBlocks.length > 0) ||
              message.thinkingContent) && (
              <div className="mb-1 w-full space-y-2.5">
                {message.thinkingBlocks?.map((block, i) => (
                  <ThinkingCard key={`think-${i}`} content={block} />
                ))}
                {message.thinkingContent && <ThinkingCard content={message.thinkingContent} />}
              </div>
            )}

            {hasContent && <AssistantTextBlock content={message.content} />}

            {/* Todo Card */}
            {message.todo && message.todo.items && message.todo.items.length > 0 && (
              <TodoCard items={message.todo.items as any} count={message.todo.count} />
            )}

            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="w-full space-y-2.5">
                {message.toolCalls.map((tool) => (
                  <ToolCard key={tool.id} tool={tool} />
                ))}
              </div>
            )}
          </>
        )}

        {message.status === 'streaming' && !hasContent && !hasSegments && (
          <div className="flex items-center gap-2 mt-1">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-60" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
            </span>
            <span className="text-xs text-foreground-subtle">生成中...</span>
          </div>
        )}
      </div>
    </div>
  );
}
