import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, Mic, Plus, Send, Sparkles, Square } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chatStore';
import { useI18n } from '@/i18n';
import { polishText } from '@/services/api';
import { AttachmentBar } from './AttachmentBar';
import { ConfigPanel } from './ConfigPanel';
import { InteractionBar } from './InteractionBar';
import { SessionOptionsRow } from './SessionOptionsRow';

interface ComposerProps {
  className?: string;
}

const LINE_HEIGHT = 22;
const MAX_COLLAPSED_ROWS = 3;
const MIN_ROWS = 1;
const MAX_EXPANDED_HEIGHT = 320;
const ACCEPTED_FILES = '.txt,.md,.markdown,.pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png,.webp,.gif';

export function Composer({ className }: ComposerProps) {
  const [text, setText] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [polishing, setPolishing] = useState(false);
  const [originalText, setOriginalText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const {
    sendMessage,
    stopGeneration,
    isStreaming,
    selectedModelId,
    pendingInteraction,
    attachments,
    addAttachment,
    removeAttachment,
  } = useChatStore();
  const { t } = useI18n();

  const handlePolish = async () => {
    const snapshot = text;
    if (!snapshot.trim() || polishing || isStreaming) return;
    setPolishing(true);
    try {
      const [polished] = await Promise.all([
        polishText(snapshot, selectedModelId),
        new Promise((resolve) => setTimeout(resolve, 400)),
      ]);
      setOriginalText(snapshot);
      setText(polished || snapshot);
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 400));
    } finally {
      setPolishing(false);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  };

  const handleRevert = () => {
    if (!originalText) return;
    setText(originalText);
    setOriginalText('');
  };

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if ((!trimmed && attachments.length === 0) || isStreaming) return;
    void sendMessage(trimmed);
    setText('');
    setExpanded(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [attachments.length, isStreaming, sendMessage, text]);

  const handleFilesSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    Array.from(event.target.files ?? []).forEach((file) => addAttachment(file));
    event.target.value = '';
  };

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key !== 'Enter') return;
      if (event.shiftKey || event.ctrlKey || event.metaKey) {
        event.preventDefault();
        const textarea = event.currentTarget;
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const next = `${text.slice(0, start)}\n${text.slice(end)}`;
        setText(next);
        requestAnimationFrame(() => {
          textarea.selectionStart = textarea.selectionEnd = start + 1;
        });
        return;
      }
      event.preventDefault();
      handleSend();
    },
    [handleSend, text],
  );

  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    const maxHeight = expanded ? MAX_EXPANDED_HEIGHT : LINE_HEIGHT * MAX_COLLAPSED_ROWS;
    textarea.style.height = `${Math.max(LINE_HEIGHT * MIN_ROWS, Math.min(textarea.scrollHeight, maxHeight))}px`;
  }, [expanded]);

  useEffect(() => {
    adjustHeight();
  }, [adjustHeight, text, expanded]);

  const canSend = Boolean(text.trim()) || attachments.length > 0;
  const showExpandToggle = text.length > 0;

  return (
    <div className={cn('flex-shrink-0 border-t border-border bg-surface px-4 py-3', className)}>
      <div className="mx-auto max-w-5xl">
        {/* Workspace selector — only before conversation starts */}
        <div className="mb-2 flex items-center gap-1">
          <SessionOptionsRow />
        </div>

        {pendingInteraction && <InteractionBar />}

        {!pendingInteraction && (
          <>
            {attachments.length > 0 && (
              <AttachmentBar
                attachments={attachments.map((attachment) => ({
                  id: attachment.id,
                  name: attachment.file.name,
                  type: attachment.file.type || 'application/octet-stream',
                  size: attachment.file.size,
                  uploading: attachment.uploading,
                }))}
                onRemove={removeAttachment}
                className="mb-0 rounded-t-[18px] border border-b-0 border-white/10 bg-[#202020]"
              />
            )}

            <div
              className={cn(
                'relative flex items-end gap-2 border border-white/10 bg-[#202020] px-3 py-2 shadow-[0_8px_30px_rgba(0,0,0,0.18)] transition-all duration-200 focus-within:border-white/[0.18] focus-within:bg-[#242424]',
                attachments.length > 0 ? 'rounded-b-[18px] rounded-t-none' : 'rounded-[18px]',
              )}
            >
              {/* ── Left: file + config ── */}
              <div className="flex items-center gap-0.5 flex-shrink-0 mb-1">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ACCEPTED_FILES}
                  multiple
                  className="hidden"
                  onChange={handleFilesSelected}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isStreaming}
                  className="rounded-md p-1.5 text-foreground-muted transition-colors hover:bg-white/[0.07] hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                  title={t('chat.new')}
                >
                  <Plus className="h-4 w-4" />
                </button>

                <ConfigPanel />
              </div>

              {/* ── Center: input ── */}
              <textarea
                ref={textareaRef}
                value={text}
                onChange={(event) => setText(event.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  isStreaming
                    ? t('chat.streaming.placeholder')
                    : `${t('chat.input.placeholder')} (${t('chat.ctrlEnter')})`
                }
                rows={1}
                disabled={isStreaming || polishing}
                className="flex-1 resize-none overflow-y-auto bg-transparent py-1 text-sm text-foreground outline-none transition-[height] duration-200 ease-out placeholder:text-foreground-subtle disabled:opacity-50"
                style={{ height: 'auto' }}
              />

              {/* ── Right: expand + polish + mic + send ── */}
              <div className="flex items-center gap-0.5 flex-shrink-0 mb-1">
                {showExpandToggle && (
                  <button
                    type="button"
                    onClick={() => setExpanded((value) => !value)}
                    className="rounded-full p-1 text-foreground-muted transition-colors hover:bg-white/[0.07] hover:text-foreground"
                    title={expanded ? t('chat.collapse') : t('chat.expand')}
                  >
                    {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                  </button>
                )}

                {/* Polish */}
                {polishing ? (
                  <button className="rounded-md p-1 text-foreground-muted" disabled title={t('chat.polish')}>
                    <Sparkles className="h-4 w-4 animate-spin" />
                  </button>
                ) : originalText ? (
                  <button
                    type="button"
                    onClick={handleRevert}
                    className="h-7 min-w-7 rounded-md px-1.5 text-sm font-semibold text-foreground-muted transition-colors hover:bg-white/[0.07] hover:text-foreground"
                    title={t('chat.revert')}
                    aria-label={t('chat.revert')}
                  >
                    ↩
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handlePolish}
                    disabled={!text.trim() || isStreaming}
                    className={cn(
                      'rounded-md p-1 transition-colors',
                      text.trim() && !isStreaming
                        ? 'text-foreground-muted hover:bg-white/[0.07] hover:text-foreground'
                        : 'cursor-not-allowed text-foreground-subtle',
                    )}
                    title={t('chat.polish')}
                    aria-label={t('chat.polish')}
                  >
                    <Sparkles className="h-4 w-4" />
                  </button>
                )}

                {/* Voice */}
                <button className="rounded-md p-1 text-foreground-muted transition-colors hover:bg-white/[0.07] hover:text-foreground">
                  <Mic className="h-4 w-4" />
                </button>

                {/* Send / Stop */}
                {isStreaming ? (
                  <button
                    type="button"
                    onClick={stopGeneration}
                    className="rounded-full bg-error p-1.5 text-white transition-all duration-200 hover:bg-error/80 hover:scale-105"
                    title={t('chat.stop')}
                  >
                    <Square className="h-3.5 w-3.5" fill="currentColor" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleSend}
                    disabled={!canSend}
                    className={cn(
                      'rounded-full p-1.5 transition-all duration-200',
                      canSend
                        ? 'bg-primary text-white hover:bg-primary-hover hover:scale-105'
                        : 'cursor-not-allowed bg-white/[0.07] text-foreground-muted',
                    )}
                  >
                    <Send className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>

            <div className="mt-1.5 text-center">
              <span className="text-[10px] text-foreground-subtle">
                AI 生成的内容可能不准确，请验证重要信息
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
