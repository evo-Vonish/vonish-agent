import { cn } from '@/lib/utils';
import type { Message } from '@/types';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ThinkingCard } from './ThinkingCard';
import { ToolCard } from './ToolCard';
import { User, Bot, Sparkles } from 'lucide-react';

interface MessageBubbleProps {
  message: Message;
  className?: string;
}

export function MessageBubble({ message, className }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';
  const hasContent = message.content && message.content.length > 0;

  return (
    <div
      className={cn(
        'group flex gap-3 px-3 sm:px-4 py-3 hover:bg-white/[0.01] transition-colors',
        isUser && 'flex-row-reverse',
        className
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm',
          isUser && 'bg-primary/15 text-primary',
          isAssistant && 'bg-success/15 text-success',
          message.role === 'system' && 'bg-warning/15 text-warning'
        )}
      >
        {isUser && <User className="w-3.5 h-3.5" />}
        {isAssistant && <Sparkles className="w-3.5 h-3.5" />}
        {message.role === 'system' && <Bot className="w-3.5 h-3.5" />}
      </div>

      {/* Content wrapper */}
      <div
        className={cn(
          'flex-1 min-w-0',
          isUser && 'flex flex-col items-end'
        )}
        style={{ maxWidth: isUser ? '85%' : '100%' }}
      >
        {/* Role label */}
        <span className="text-[10px] text-foreground-subtle mb-1.5 font-medium select-none">
          {isUser ? '你' : isAssistant ? 'Assistant' : 'System'}
        </span>

        {/* Thinking content — per-round blocks + current streaming block */}
        {((message.thinkingBlocks && message.thinkingBlocks.length > 0) || message.thinkingContent) && (
          <div className="space-y-2 mb-2 w-full">
            {message.thinkingBlocks?.map((block, i) => (
              <ThinkingCard key={`think-${i}`} content={block} />
            ))}
            {message.thinkingContent && (
              <ThinkingCard content={message.thinkingContent} />
            )}
          </div>
        )}

        {/* Main message content — rendered BEFORE tool cards so streamed text
            that arrives before/during tool execution stays above the tools */}
        {hasContent && (
          <div
            className={cn(
              'rounded-2xl mb-2',
              isUser
                ? 'bg-primary/15 text-foreground px-4 py-2.5 border border-primary/10'
                : 'bg-surface text-foreground w-full px-1 py-0.5'
            )}
            style={{ maxWidth: isUser ? '100%' : undefined }}
          >
            <MarkdownRenderer content={message.content} />
          </div>
        )}

        {/* Tool calls — rendered below content so they don't push text down */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className={cn('space-y-2 w-full', isUser ? 'max-w-full' : 'max-w-full')}>
            {message.toolCalls.map((tool) => (
              <ToolCard key={tool.id} tool={tool} />
            ))}
          </div>
        )}

        {/* Streaming indicator */}
        {message.status === 'streaming' && !hasContent && (
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
