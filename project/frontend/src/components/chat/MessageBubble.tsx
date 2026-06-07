import { Bot, Copy, FileText, Image, MessageSquareQuote, Sparkles, User } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatBytes } from '@/lib/utils';
import type { ArtifactRef, Message, MessageSegment, Reference, UploadedFileMeta } from '@/types';
import { useI18n } from '@/i18n';
import { useChatStore } from '@/stores/chatStore';
import { useWorkbenchStore } from '@/stores/workbenchStore';
import { useReferenceStore, type NewReference } from '@/stores/referenceStore';
import { useInlinePromptStore } from '@/stores/inlinePromptStore';
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
    <div className="mb-1 w-full px-0.5 py-1 text-[15px] leading-7 text-[#e8e6e3]">
      <div data-quote-source="chat">
        <MarkdownRenderer content={content} />
      </div>
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

  if (segment.type === 'artifact') {
    return <ArtifactCard artifact={segment.artifact} />;
  }

  return <AssistantTextBlock content={segment.content} />;
}

function FileIcon({ file }: { file: UploadedFileMeta }) {
  if (file.mimeType?.startsWith('image/')) return <Image className="h-3.5 w-3.5 text-primary" />;
  return <FileText className="h-3.5 w-3.5 text-foreground-subtle" />;
}

function CardActions({ draft, copyText }: { draft: NewReference; copyText: string }) {
  const addReference = useReferenceStore((state) => state.addReference);
  const openPrompt = useInlinePromptStore((state) => state.openPrompt);
  const copy = () => void navigator.clipboard?.writeText(copyText).catch(() => {});
  return (
    <span className="ml-auto flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          addReference(draft);
        }}
        className="rounded p-1 text-[#5c5855] transition-colors hover:bg-white/10 hover:text-[#e8e6e3]"
        title="引用"
      >
        <MessageSquareQuote className="h-3 w-3" />
      </button>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          openPrompt(draft, { left: Math.max(16, window.innerWidth / 2 - 170), top: Math.max(16, window.innerHeight - 250) });
        }}
        className="rounded p-1 text-[#5c5855] transition-colors hover:bg-white/10 hover:text-[#e0a072]"
        title="问 AI"
      >
        <Sparkles className="h-3 w-3" />
      </button>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          copy();
        }}
        className="rounded p-1 text-[#5c5855] transition-colors hover:bg-white/10 hover:text-[#e8e6e3]"
        title="复制"
      >
        <Copy className="h-3 w-3" />
      </button>
    </span>
  );
}

function FileCard({ file, conversationId }: { file: UploadedFileMeta; conversationId: string | null }) {
  const openInWorkbench = useWorkbenchStore((state) => state.openFile);
  const canOpen = Boolean(conversationId && file.workspacePath);
  const openFile = () => {
    if (!canOpen || !conversationId) return;
    // Open the uploaded/generated file as an editable workbench tab.
    void openInWorkbench(conversationId, file.workspacePath);
  };
  const draft: NewReference = {
    sourceType: 'artifact-block',
    sourceId: file.id,
    title: file.originalName,
    preview: `Uploaded file: ${file.originalName}\nPath: ${file.workspacePath}\nType: ${file.mimeType}\nSize: ${formatBytes(file.size)}`,
    location: {
      filePath: file.workspacePath,
      workspaceId: conversationId ?? undefined,
    },
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={openFile}
      onKeyDown={(event) => {
        if ((event.key === 'Enter' || event.key === ' ') && canOpen) openFile();
      }}
      className={cn(
        'group flex max-w-[320px] items-center gap-2 rounded-lg border px-2.5 py-2 text-left text-xs transition-colors',
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
      <CardActions draft={draft} copyText={draft.preview} />
    </div>
  );
}

function ReferenceHistoryCard({ ref }: { ref: Reference }) {
  const openFile = useWorkbenchStore((state) => state.openFile);
  const focusSource = () => {
    if (ref.location?.filePath) {
      void openFile(ref.location.workspaceId ?? null, ref.location.filePath, {
        reveal: {
          lineStart: ref.location.lineStart,
          lineEnd: ref.location.lineEnd,
          blockId: ref.location.blockId,
          elementId: ref.location.elementId,
          cssPath: ref.location.cssPath,
          pageIndex: ref.location.pageIndex,
          sheetName: ref.location.sheetName,
          cellRange: ref.location.cellRange,
          slideIndex: ref.location.slideIndex,
        },
      });
      return;
    }
    if (ref.location?.messageId) {
      const el = document.querySelector(`[data-msg-id="${ref.location.messageId}"]`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };
  const draft: NewReference = {
    sourceType: ref.sourceType,
    sourceId: ref.sourceId,
    title: ref.title,
    preview: ref.preview,
    instruction: ref.instruction,
    location: ref.location,
    payload: ref.payload,
  };
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={focusSource}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') focusSource();
      }}
      className="group flex max-w-[320px] items-center gap-2 rounded-lg border border-white/10 bg-white/[0.035] px-2.5 py-2 text-left text-xs text-[#e8e6e3] transition-colors hover:border-primary/30 hover:bg-white/[0.055]"
      data-quote-card="reference"
    >
      <MessageSquareQuote className="h-3.5 w-3.5 shrink-0 text-[#c66a38]" />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium">{ref.title}</span>
        <span className="block truncate text-[10px] text-foreground-subtle">{ref.sourceType}</span>
      </span>
      <CardActions draft={draft} copyText={`${ref.title}\n${ref.preview}`} />
    </div>
  );
}

function ArtifactCard({ artifact }: { artifact: ArtifactRef }) {
  const openInWorkbench = useWorkbenchStore((state) => state.openFile);
  const openFile = () => {
    if (!artifact.path) return;
    void openInWorkbench(artifact.workspaceId ?? null, artifact.path);
  };
  const draft: NewReference = {
    sourceType: 'artifact-block',
    sourceId: artifact.id,
    title: artifact.title,
    preview: `Agent artifact: ${artifact.title}\nPath: ${artifact.path}${artifact.description ? `\n${artifact.description}` : ''}`,
    location: {
      filePath: artifact.path,
      workspaceId: artifact.workspaceId ?? undefined,
    },
  };
  return (
    <div className="relative pl-9 text-[#9a9590]">
      <span className="workflow-rail-icon"><FileText className="h-4 w-4" /></span>
      <div
        role="button"
        tabIndex={0}
        onClick={openFile}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') openFile();
        }}
        className="group flex max-w-[420px] items-center gap-2 rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2 text-left text-xs text-[#e8e6e3] transition-colors hover:border-primary/30 hover:bg-white/[0.055]"
        data-quote-card="artifact"
      >
        <FileText className="h-3.5 w-3.5 shrink-0 text-[#c66a38]" />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium">{artifact.title}</span>
          <span className="block truncate text-[10px] text-foreground-subtle">{artifact.path}</span>
        </span>
        <CardActions draft={draft} copyText={draft.preview} />
      </div>
    </div>
  );
}

export function MessageBubble({ message, className }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';
  const hasContent = message.content && message.content.length > 0;
  const hasSegments = Boolean(message.segments?.length);
  const { t } = useI18n();
  const conversationId = useChatStore((state) => state.currentConversationId);
  const workspaceId = useChatStore((state) => {
    const currentId = state.currentConversationId;
    const conversation = state.conversations.find((item) => item.id === currentId);
    return String(conversation?.metadata?.workspace_id || conversation?.metadata?.project_id || currentId || '');
  });

  return (
    <div
      data-msg-id={message.id}
      className={cn(
        'group flex gap-3 py-2.5 transition-colors',
        isUser && 'flex-row-reverse',
        className,
      )}
    >
      <div
        className={cn(
          'w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5',
          isUser && 'text-[#9a9590]',
          isAssistant && 'bg-[rgba(90,138,94,0.16)] text-[#67d28b]',
          message.role === 'system' && 'text-warning',
        )}
      >
        {isUser && <User className="w-3.5 h-3.5" />}
        {isAssistant && <Sparkles className="w-3.5 h-3.5" />}
        {message.role === 'system' && <Bot className="w-3.5 h-3.5" />}
      </div>

      <div className={cn('min-w-0', isUser ? 'ml-auto flex w-auto max-w-[76%] flex-col items-end' : 'flex-1')}>
        <span className="mb-1.5 select-none text-[10px] font-medium text-[#5c5855]">
          {isUser ? t('user.label') : isAssistant ? t('assistant.label') : t('system.label')}
        </span>

        {isUser && hasContent && (
          <div
            data-quote-source="chat"
            data-quote-msg={message.id}
            className="mb-1 max-w-full rounded-[10px] rounded-tr px-4 py-3 text-left text-[#e8e6e3] shadow-[0_8px_28px_rgba(0,0,0,0.18)]"
            style={{
              maxWidth: '100%',
              background: 'rgba(255, 255, 255, 0.045)',
              border: '1px solid rgba(255, 255, 255, 0.07)',
            }}
          >
            <MarkdownRenderer content={message.content} />
          </div>
        )}

        {isUser && ((message.files && message.files.length > 0) || (message.references && message.references.length > 0)) && (
          <div className="mb-2 flex max-w-full flex-wrap justify-end gap-2">
            {message.files?.map((file) => (
              <FileCard key={file.id} file={file} conversationId={workspaceId || conversationId} />
            ))}
            {message.references?.map((ref) => (
              <ReferenceHistoryCard key={ref.id} ref={ref} />
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
          <div className="mt-1 flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-60" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
            </span>
            <span className="font-mono-code text-xs text-[#9a9590]">生成中...</span>
          </div>
        )}
      </div>
    </div>
  );
}
