import { useState, useRef, useCallback } from 'react';
import { Send, Paperclip, Mic, Sparkles, Square } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chatStore';
import { useI18n } from '@/i18n';
import { ModelSelector } from './ModelSelector';

interface ComposerProps {
  className?: string;
}

export function Composer({ className }: ComposerProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { sendMessage, stopGeneration, isStreaming } = useChatStore();
  const { t } = useI18n();

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming) return;
    sendMessage(trimmed);
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [text, isStreaming, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleInput = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, []);

  return (
    <div
      className={cn(
        'border-t border-border bg-surface px-4 py-3 flex-shrink-0',
        className
      )}
    >
      <div className="max-w-5xl mx-auto">
        {/* Toolbar */}
        <div className="flex items-center gap-1 mb-2">
          <ModelSelector />
          <button className="p-1.5 rounded-md hover:bg-surface-hover text-foreground-muted hover:text-foreground transition-colors">
            <Paperclip className="w-4 h-4" />
          </button>
          <button className="p-1.5 rounded-md hover:bg-surface-hover text-foreground-muted hover:text-foreground transition-colors">
            <Mic className="w-4 h-4" />
          </button>
          <button className="p-1.5 rounded-md hover:bg-surface-hover text-foreground-muted hover:text-foreground transition-colors ml-auto">
            <Sparkles className="w-4 h-4" />
          </button>
        </div>

        {/* Input area */}
        <div className="relative flex items-end gap-2 bg-background border border-border rounded-xl px-3 py-2 focus-within:border-primary/50 transition-colors">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              handleInput();
            }}
            onKeyDown={handleKeyDown}
            placeholder={isStreaming ? t('chat.streaming.placeholder') : `${t('chat.input.placeholder')} (${t('chat.ctrlEnter')})`}
            rows={1}
            disabled={isStreaming}
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-foreground-subtle resize-none outline-none max-h-[200px] py-1 disabled:opacity-50"
          />
          {isStreaming ? (
            <button
              onClick={stopGeneration}
              className="p-2 rounded-lg transition-all flex-shrink-0 mb-0.5 bg-error text-white hover:bg-error/80 animate-pulse"
              title={t('chat.stop')}
            >
              <Square className="w-4 h-4" fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!text.trim()}
              className={cn(
                'p-2 rounded-lg transition-all flex-shrink-0 mb-0.5',
                text.trim()
                  ? 'bg-primary text-white hover:bg-primary-hover'
                  : 'bg-surface-hover text-foreground-muted cursor-not-allowed'
              )}
            >
              <Send className="w-4 h-4" />
            </button>
          )}
        </div>

        <div className="text-center mt-1.5">
          <span className="text-[10px] text-foreground-subtle">
            AI 生成的内容可能不准确，请验证重要信息
          </span>
        </div>
      </div>
    </div>
  );
}
