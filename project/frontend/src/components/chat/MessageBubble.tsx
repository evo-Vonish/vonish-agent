import { Bot, Sparkles, User } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Message, MessageSegment } from '@/types';
import { useI18n } from '@/i18n';
import { useChatStore } from '@/stores/chatStore';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ThinkingCard } from './ThinkingCard';
import { ToolCard } from './ToolCard';
import { TodoCard } from './TodoCard';
import { InteractionCard } from './InteractionCard';

interface MessageBubbleProps {
  message: Message;
  className?: string;
}

function AssistantTextBlock({ content }: { content: string }) {
  if (!content) return null;
  return (
    <div className="rounded-2xl mb-2 bg-surface text-foreground w-full px-1 py-0.5">
      <MarkdownRenderer content={content} />
    </div>
  );
}

function SegmentRenderer({ segment }: { segment: MessageSegment }) {
  if (segment.type === 'thinking') {
    return (
      <ThinkingCard
        content={segment.content}
        summary={segment.summary}
        status={segment.status}
      />
    );
  }

  if (segment.type === 'tool') {
    return <ToolCard tool={segment.tool} />;
  }

  return <AssistantTextBlock content={segment.content} />;
}

export function MessageBubble({ message, className }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';
  const hasContent = message.content && message.content.length > 0;
  const hasSegments = Boolean(message.segments?.length);
  const { t } = useI18n();
  const respondToInteraction = useChatStore((s) => s.respondToInteraction);
  const conversationId = useChatStore((s) => s.currentConversationId);

  return (
    <div
      className={cn(
        'group flex gap-3 px-3 sm:px-4 py-3 hover:bg-white/[0.01] transition-colors',
        isUser && 'flex-row-reverse',
        className,
      )}
    >
      <div
        className={cn(
          'w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm',
          isUser && 'bg-primary/15 text-primary',
          isAssistant && 'bg-success/15 text-success',
          message.role === 'system' && 'bg-warning/15 text-warning',
        )}
      >
        {isUser && <User className="w-3.5 h-3.5" />}
        {isAssistant && <Sparkles className="w-3.5 h-3.5" />}
        {message.role === 'system' && <Bot className="w-3.5 h-3.5" />}
      </div>

      <div
        className={cn('flex-1 min-w-0', isUser && 'flex flex-col items-end')}
        style={{ maxWidth: isUser ? '85%' : '100%' }}
      >
        <span className="text-[10px] text-foreground-subtle mb-1.5 font-medium select-none">
          {isUser ? t('user.label') : isAssistant ? t('assistant.label') : t('system.label')}
        </span>

        {isUser && hasContent && (
          <div
            className="rounded-2xl mb-2 bg-primary/15 text-foreground px-4 py-2.5 border border-primary/10"
            style={{ maxWidth: '100%' }}
          >
            <MarkdownRenderer content={message.content} />
          </div>
        )}

        {isAssistant && hasSegments && (
          <div className="space-y-2 w-full">
            {message.segments?.map((segment) => (
              <SegmentRenderer key={segment.id} segment={segment} />
            ))}
          </div>
        )}

        {isAssistant && !hasSegments && (
          <>
            {((message.thinkingBlocks && message.thinkingBlocks.length > 0) ||
              message.thinkingContent) && (
              <div className="space-y-2 mb-2 w-full">
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

            {/* Interaction Card */}
            {message.interaction && message.interaction.interaction_id && (
              <InteractionCard
                payload={{
                  interaction_id: message.interaction.interaction_id,
                  type: message.interaction.type,
                  title: message.interaction.title,
                  description: message.interaction.description,
                  options: message.interaction.options,
                  allow_custom_response: message.interaction.allow_custom_response,
                  risk_level: message.interaction.risk_level,
                  plan: message.interaction.plan,
                }}
                conversationId={conversationId ?? ''}
                onRespond={respondToInteraction}
                resolved={message.interaction.resolved}
                resolvedChoice={message.interaction.response?.choice}
              />
            )}

            {message.toolCalls && message.toolCalls.length > 0 && (
              <div className="space-y-2 w-full">
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
