import { useState, useRef, useCallback, useEffect } from 'react';
import { Send, Paperclip, Mic, Sparkles, Square, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chatStore';
import { useI18n } from '@/i18n';
import { ModelSelector } from './ModelSelector';
import { ContextButton } from './ContextButton';

interface ComposerProps {
  className?: string;
}

const LINE_HEIGHT = 22; // px, matches text-sm line-height roughly
const MAX_COLLAPSED_ROWS = 3;
const MIN_ROWS = 1;
const MAX_EXPANDED_HEIGHT = 320; // px

export function Composer({ className }: ComposerProps) {
  const [text, setText] = useState('');
  const [expanded, setExpanded] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { sendMessage, stopGeneration, isStreaming } = useChatStore();
  const { t } = useI18n();

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || isStreaming) return;
    sendMessage(trimmed);
    setText('');
    setExpanded(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [text, isStreaming, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        if (e.shiftKey || e.ctrlKey || e.metaKey) {
          // Ctrl/Cmd/Shift + Enter = insert newline
          e.preventDefault();
          const ta = e.currentTarget as HTMLTextAreaElement;
          const start = ta.selectionStart;
          const end = ta.selectionEnd;
          const newValue = text.slice(0, start) + '\n' + text.slice(end);
          setText(newValue);
          // Restore cursor position after newline
          requestAnimationFrame(() => {
            ta.selectionStart = ta.selectionEnd = start + 1;
          });
        } else {
          // Plain Enter = send
          e.preventDefault();
          handleSend();
        }
      }
    },
    [text, handleSend]
  );

  const adjustHeight = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    const scrollH = ta.scrollHeight;
    const maxHeight = expanded ? MAX_EXPANDED_HEIGHT : LINE_HEIGHT * MAX_COLLAPSED_ROWS;
    ta.style.height = `${Math.max(LINE_HEIGHT * MIN_ROWS, Math.min(scrollH, maxHeight))}px`;
  }, [expanded]);

  useEffect(() => {
    adjustHeight();
  }, [text, expanded, adjustHeight]);

  const showExpandToggle = text.length > 0;
  const canExpandMore = expanded === false && text.length > 0;

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
          <ContextButton />
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
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isStreaming ? t('chat.streaming.placeholder') : `${t('chat.input.placeholder')} (${t('chat.ctrlEnter')})`}
            rows={1}
            disabled={isStreaming}
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-foreground-subtle resize-none outline-none py-1 disabled:opacity-50 transition-[height] duration-200 ease-out overflow-y-auto"
            style={{ height: 'auto' }}
          />

          {/* Expand / collapse toggle */}
          {showExpandToggle && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="p-1 rounded-md hover:bg-surface-hover text-foreground-muted hover:text-foreground transition-colors flex-shrink-0 mb-1"
              title={expanded ? t('chat.collapse') : t('chat.expand')}
            >
              {expanded ? (
                <ChevronUp className="w-3.5 h-3.5" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5" />
              )}
            </button>
          )}

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
