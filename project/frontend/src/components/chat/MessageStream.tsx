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
  const editingTurn = useChatStore((s) => s.editingTurn);
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
          'px-4 py-5',
          className
        )}
      >
        <div className="message-stream-shell mx-auto w-full space-y-1">
          {(() => {
            // Dim all messages that follow the one being edited — they will be wiped on send.
            const editingId = editingTurn?.messageId ?? null;
            let pastEdit = false;
            return messages.map((msg: Message) => {
              const isDimmed = pastEdit;
              if (editingId && msg.id === editingId) pastEdit = true;
              return <MessageBubble key={msg.id} message={msg} dimmed={isDimmed} />;
            });
          })()}
          <div ref={bottomRef} className="h-2" />
        </div>
      </div>

      {/* Scroll to bottom button */}
      {showScrollBtn && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 right-4 z-10 rounded-full border border-white/[0.08] bg-[#252423]/90 p-2 shadow-[0_16px_40px_rgba(0,0,0,0.42)] backdrop-blur-xl transition-colors hover:bg-white/[0.08]"
        >
          <MessageSquare className="h-4 w-4 text-[#9a9590]" />
        </button>
      )}
    </>
  );
}
