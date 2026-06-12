import {
  ArrowUpRight,
  Bot,
  ChevronRight,
  Copy,
  FileCode2,
  FileSpreadsheet,
  FileText,
  FileType2,
  Globe2,
  HardDrive,
  Image,
  MessageSquareQuote,
  Pencil,
  Presentation,
  RotateCcw,
  Sparkles,
  User,
} from 'lucide-react';
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
import { elementPopoverPosition } from '@/lib/selectionRef';

interface MessageBubbleProps {
  message: Message;
  className?: string;
  /** When true, render with reduced opacity and block interaction (messages queued for wipe on edit/retry). */
  dimmed?: boolean;
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
    <span className="ml-auto hidden shrink-0 items-center gap-0.5 group-hover:flex group-focus-within:flex">
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
          openPrompt(draft, elementPopoverPosition(event.currentTarget, 340, 150));
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

function artifactExtension(path: string) {
  const file = path.split(/[\\/]/).pop() || path;
  const dot = file.lastIndexOf('.');
  return dot >= 0 ? file.slice(dot + 1).toLowerCase() : '';
}

function ArtifactIcon({ artifact }: { artifact: ArtifactRef }) {
  const ext = artifactExtension(artifact.path);
  const mime = artifact.mimeType || '';
  const cls = 'h-5 w-5';
  if (mime.startsWith('image/')) return <Image className={cls} />;
  if (['html', 'htm'].includes(ext)) return <Globe2 className={cls} />;
  if (['py', 'ts', 'tsx', 'js', 'jsx', 'json', 'css'].includes(ext)) return <FileCode2 className={cls} />;
  if (['ppt', 'pptx'].includes(ext)) return <Presentation className={cls} />;
  if (['xls', 'xlsx', 'csv'].includes(ext)) return <FileSpreadsheet className={cls} />;
  if (['pdf', 'doc', 'docx', 'md', 'txt'].includes(ext)) return <FileType2 className={cls} />;
  return <FileText className={cls} />;
}

function artifactTypeLabel(artifact: ArtifactRef) {
  const ext = artifactExtension(artifact.path);
  if (artifact.kind) return artifact.kind;
  if (ext) return ext.toUpperCase();
  if (artifact.mimeType) return artifact.mimeType;
  return 'Artifact';
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
  const typeLabel = artifactTypeLabel(artifact);
  return (
    <div className="relative my-1 pl-9 text-[#9a9590]">
      <span className="workflow-rail-icon border-[#c66a38]/35 bg-[#1f160f] text-[#e0a072]">
        <ArtifactIcon artifact={artifact} />
      </span>
      <div
        role="button"
        tabIndex={0}
        onClick={openFile}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') openFile();
        }}
        className="group w-full max-w-[680px] overflow-hidden rounded-xl border border-[#c66a38]/20 bg-[linear-gradient(145deg,rgba(36,30,26,0.92),rgba(21,20,19,0.92))] text-left text-xs text-[#e8e6e3] shadow-[0_14px_38px_rgba(0,0,0,0.28),inset_0_1px_0_rgba(255,255,255,0.055)] transition hover:border-[#d18a5b]/42 hover:bg-[linear-gradient(145deg,rgba(43,35,30,0.96),rgba(24,23,22,0.96))]"
        data-quote-card="artifact"
      >
        <div className="flex items-start gap-3 px-4 py-3.5">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-[#c66a38]/25 bg-[#2a1b12] text-[#e0a072] shadow-[inset_0_1px_0_rgba(255,255,255,0.07)]">
            <ArtifactIcon artifact={artifact} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2">
              <span className="truncate text-[14px] font-semibold tracking-normal text-[#f4eee8]">{artifact.title}</span>
              <span className="shrink-0 rounded-md border border-[#c66a38]/20 bg-[#c66a38]/10 px-1.5 py-0.5 text-[10px] font-medium uppercase text-[#e0a072]">
                {typeLabel}
              </span>
            </div>
            <div className="mt-1 truncate font-mono-code text-[11px] text-[#9c938b]">{artifact.path}</div>
            {artifact.description && (
              <div className="mt-2 line-clamp-2 max-w-[560px] text-[12px] leading-5 text-[#c9c2ba]">
                {artifact.description}
              </div>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] text-[#8f8780]">
              {artifact.size !== undefined && (
                <span className="inline-flex items-center gap-1 rounded-md bg-white/[0.045] px-2 py-1">
                  <HardDrive className="h-3 w-3" />
                  {formatBytes(artifact.size)}
                </span>
              )}
              {artifact.mimeType && (
                <span className="max-w-[240px] truncate rounded-md bg-white/[0.045] px-2 py-1">{artifact.mimeType}</span>
              )}
              {artifact.sourceToolCallId && (
                <span className="truncate rounded-md bg-white/[0.035] px-2 py-1">tool {artifact.sourceToolCallId}</span>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <CardActions draft={draft} copyText={draft.preview} />
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/[0.045] text-[#9c938b] transition group-hover:bg-[#c66a38]/16 group-hover:text-[#f2b083]">
              <ArrowUpRight className="h-4 w-4" />
            </span>
          </div>
        </div>
        <div className="flex items-center justify-between border-t border-white/[0.06] bg-black/10 px-4 py-2 text-[11px] text-[#8f8780]">
          <span>已提交到右侧工作台，可预览、选择内容并引用修改</span>
          <span className="inline-flex items-center gap-1 text-[#bfa08a]">
            打开
            <ChevronRight className="h-3.5 w-3.5" />
          </span>
        </div>
      </div>
    </div>
  );
}

export function MessageBubble({ message, className, dimmed }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';
  const hasContent = message.content && message.content.length > 0;
  const hasSegments = Boolean(message.segments?.length);
  const { t } = useI18n();
  const conversationId = useChatStore((state) => state.currentConversationId);
  const isStreaming = useChatStore((state) => state.isStreaming);
  const beginEditMessage = useChatStore((state) => state.beginEditMessage);
  const retryMessage = useChatStore((state) => state.retryMessage);
  const workspaceId = useChatStore((state) => {
    const currentId = state.currentConversationId;
    const conversation = state.conversations.find((item) => item.id === currentId);
    return String(conversation?.metadata?.workspace_id || conversation?.metadata?.project_id || currentId || '');
  });

  return (
    <div
      data-msg-id={message.id}
      className={cn(
        'group flex gap-3 py-2.5 transition-all duration-300',
        isUser && 'flex-row-reverse',
        dimmed && 'pointer-events-none select-none opacity-30',
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
          <div className="group/user relative mb-1 max-w-full">
            <div
              data-quote-source="chat"
              data-quote-msg={message.id}
              className="max-w-full rounded-[10px] rounded-tr px-4 py-3 text-left text-[#e8e6e3] shadow-[0_8px_28px_rgba(0,0,0,0.18)]"
              style={{
                maxWidth: '100%',
                background: 'rgba(255, 255, 255, 0.045)',
                border: '1px solid rgba(255, 255, 255, 0.07)',
              }}
            >
              <MarkdownRenderer content={message.content} />
            </div>
            <div className="absolute -bottom-7 right-1 z-10 hidden items-center gap-1 rounded-lg border border-white/10 bg-[#1f1f1f]/95 p-1 shadow-xl backdrop-blur group-hover/user:flex group-focus-within/user:flex">
              <button
                type="button"
                onClick={() => void navigator.clipboard?.writeText(message.content).catch(() => {})}
                className="rounded-md p-1 text-[#9a9590] hover:bg-white/10 hover:text-[#e8e6e3]"
                title="复制"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                disabled={isStreaming}
                onClick={() => beginEditMessage(message.id)}
                className="rounded-md p-1 text-[#9a9590] hover:bg-white/10 hover:text-[#e8e6e3] disabled:cursor-not-allowed disabled:opacity-40"
                title="修改"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                disabled={isStreaming}
                onClick={() => void retryMessage(message.id)}
                className="rounded-md p-1 text-[#9a9590] hover:bg-white/10 hover:text-[#e8e6e3] disabled:cursor-not-allowed disabled:opacity-40"
                title="重试"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </button>
            </div>
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
            {message.segments?.map((segment, index) => (
              <SegmentRenderer key={`${segment.id}-${index}`} segment={segment} />
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
                {message.toolCalls.map((tool, index) => (
                  <ToolCard key={`${tool.id}-${index}`} tool={tool} />
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
