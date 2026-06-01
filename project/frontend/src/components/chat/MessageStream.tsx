import { useRef, useEffect, useState, useCallback } from 'react';
import { cn } from '@/lib/utils';
import type { Message } from '@/types';
import { MessageBubble } from './MessageBubble';
import { WelcomeScreen } from './WelcomeScreen';
import { useChatStore } from '@/stores/chatStore';
import { MessageSquare } from 'lucide-react';

interface MessageStreamProps {
  className?: string;
}

export function MessageStream({ className }: MessageStreamProps) {
  const messages = useChatStore((s) => s.messages);
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

  // Empty state — Welcome Screen
  if (messages.length === 0) {
    return <WelcomeScreen />;
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
        <div className="message-stream-shell mx-auto w-full space-y-0.5">
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
