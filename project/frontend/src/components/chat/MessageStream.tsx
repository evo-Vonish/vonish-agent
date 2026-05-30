import { useRef, useEffect, useState, useCallback } from 'react';
import { cn } from '@/lib/utils';
import type { Message } from '@/types';
import { MessageBubble } from './MessageBubble';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useI18n } from '@/i18n';
import { MessageSquare, Zap, Code2, Database, FileCode, Palette } from 'lucide-react';
import { suggestionQuestions } from '@/services/mockData';

interface MessageStreamProps {
  className?: string;
}

const quickActions = [
  { icon: Code2, key: 'chat.empty.code', color: 'text-blue-400' },
  { icon: Database, key: 'chat.empty.analysis', color: 'text-green-400' },
  { icon: FileCode, key: 'chat.empty.debug', color: 'text-yellow-400' },
  { icon: Palette, key: 'chat.empty.design', color: 'text-purple-400' },
];

export function MessageStream({ className }: MessageStreamProps) {
  const messages = useChatStore((s) => s.messages);
  const { sendMessage } = useChatStore();
  const { isMobile } = useUIStore();
  const { t } = useI18n();
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [userScrolled, setUserScrolled] = useState(false);
  const [showScrollBtn, setShowScrollBtn] = useState(false);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (!userScrolled && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, userScrolled]);

  // Track user scroll
  const handleScroll = useCallback(() => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const nearBottom = scrollHeight - scrollTop - clientHeight < 100;
    setUserScrolled(!nearBottom);
    setShowScrollBtn(!nearBottom);
  }, []);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    setUserScrolled(false);
    setShowScrollBtn(false);
  }, []);

  // Empty state
  if (messages.length === 0) {
    return (
      <div
        className={cn(
          'flex-1 flex flex-col items-center justify-center overflow-y-auto',
          className
        )}
      >
        <div className="text-center space-y-5 px-4 max-w-lg">
          {/* Logo */}
          <div className="w-14 h-14 rounded-2xl bg-surface border border-border flex items-center justify-center mx-auto shadow-lg">
            <Zap className="w-7 h-7 text-primary" />
          </div>

          <div>
            <h2 className="text-lg font-semibold text-foreground mb-1.5">{t('chat.empty')}</h2>
            <p className="text-xs text-foreground-subtle leading-relaxed">{t('chat.empty.desc')}</p>
          </div>

          {/* Quick actions */}
          <div className={cn('grid gap-2', isMobile ? 'grid-cols-2' : 'grid-cols-4')}>
            {quickActions.map((action) => (
              <button
                key={action.key}
                onClick={() => sendMessage(t(action.key))}
                className="flex flex-col items-center gap-1.5 p-3 rounded-xl bg-surface border border-border hover:border-primary/30 hover:bg-surface-hover transition-all group"
              >
                <action.icon className={cn('w-5 h-5', action.color)} />
                <span className="text-[10px] text-foreground-muted group-hover:text-foreground transition-colors">
                  {t(action.key)}
                </span>
              </button>
            ))}
          </div>

          {/* Suggestion questions */}
          <div className="space-y-2">
            <p className="text-[10px] text-foreground-subtle uppercase tracking-wider">{t('chat.try')}</p>
            <div className="space-y-1.5">
              {suggestionQuestions.slice(0, isMobile ? 3 : 5).map((q, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(q)}
                  className="w-full text-left px-3 py-2 rounded-lg bg-surface border border-border hover:border-primary/30 hover:bg-surface-hover transition-all text-xs text-foreground-muted hover:text-foreground"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className={cn(
          'flex-1 overflow-y-auto overflow-x-hidden scroll-smooth',
          'py-4',
          className
        )}
      >
        <div className="max-w-5xl mx-auto w-full space-y-1">
          {messages.map((msg: Message) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} className="h-2" />
        </div>
      </div>

      {/* Scroll to bottom button */}
      {showScrollBtn && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 right-4 z-10 p-2 rounded-full bg-surface-elevated border border-border shadow-lg hover:bg-surface-hover transition-colors"
        >
          <MessageSquare className="w-4 h-4 text-foreground-muted" />
        </button>
      )}
    </>
  );
}
