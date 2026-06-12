import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, Mic, Plus, Send, Sparkles, Square } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useI18n } from '@/i18n';
import { polishText } from '@/services/api';
import { ComposerContextBar } from './ComposerContextBar';
import { ConfigPanel } from './ConfigPanel';
import { InteractionBar } from './InteractionBar';
import { SessionOptionsRow } from './SessionOptionsRow';
import { useReferenceStore } from '@/stores/referenceStore';

interface ComposerProps {
  className?: string;
}

const LINE_HEIGHT = 22;
const MAX_COLLAPSED_ROWS = 3;
const MIN_ROWS = 1;
const MAX_EXPANDED_HEIGHT = 320;
const ACCEPTED_FILES = '.txt,.md,.markdown,.pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png,.webp,.gif';
const modePlaceholders = {
  chat: 'Ask, compare, or reason through evidence',
  work: 'Describe a document, file, or office task',
  code: 'Describe a code task or ask about the workspace',
};

export function Composer({ className }: ComposerProps) {
  const [text, setText] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [polishing, setPolishing] = useState(false);
  const [originalText, setOriginalText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const {
    sendMessage,
    inputText,
    setInputText,
    stopGeneration,
    isStreaming,
    selectedModelId,
    pendingInteraction,
    editingTurn,
    cancelEditMessage,
    contextUsage,
    attachments,
    addAttachment,
    removeAttachment,
  } = useChatStore();
  const referenceCount = useReferenceStore((state) => state.references.length);
  const activeMode = useUIStore((state) => state.activeMode);
  const { t } = useI18n();
  const contextLimitReached = Boolean(
    contextUsage && contextUsage.totalTokens >= contextUsage.maxTokens,
  );

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
      setInputText(polished || snapshot);
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
    setInputText(originalText);
    setOriginalText('');
  };

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if ((!trimmed && attachments.length === 0 && referenceCount === 0) || isStreaming || contextLimitReached) return;
    void sendMessage(trimmed);
    setText('');
    setInputText('');
    setExpanded(false);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [attachments.length, contextLimitReached, isStreaming, referenceCount, sendMessage, setInputText, text]);

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
        setInputText(next);
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

  useEffect(() => {
    if (inputText !== text) setText(inputText);
  }, [inputText]);

  const canSend = !contextLimitReached && (Boolean(text.trim()) || attachments.length > 0 || referenceCount > 0);
  const showExpandToggle = text.length > 0;

  return (
    <div
      className={cn('relative z-20 flex-shrink-0 border-t border-border bg-background/86 px-4 py-3 shadow-[0_-18px_48px_rgba(0,0,0,0.28)] backdrop-blur-xl', className)}
    >
      <div className="mx-auto max-w-[900px]">
        {/* Workspace selector — only before conversation starts */}
        <div className="mb-2 flex items-center gap-1">
          <SessionOptionsRow />
        </div>

        {pendingInteraction && <InteractionBar />}

        {!pendingInteraction && (
          <>
            {editingTurn && (
              <div className="mb-2 flex items-center justify-between rounded-xl border border-[#c66a38]/25 bg-[#2a1b12]/80 px-3 py-2 text-xs text-[#e8c7aa]">
                <span className="truncate">正在修改上一条消息，发送后会回滚并重跑后续工作流</span>
                <button
                  type="button"
                  onClick={() => {
                    cancelEditMessage();
                    setText('');
                  }}
                  className="ml-3 rounded-md px-2 py-1 text-[#d7b79e] hover:bg-white/10 hover:text-white"
                >
                  取消
                </button>
              </div>
            )}

            {(attachments.length > 0 || referenceCount > 0) && (
              <ComposerContextBar
                attachments={attachments.map((attachment) => ({
                  id: attachment.id,
                  name: attachment.file.name,
                  type: attachment.file.type || 'application/octet-stream',
                  size: attachment.file.size,
                  uploading: attachment.uploading,
                }))}
                onRemoveAttachment={removeAttachment}
                className="mb-0 rounded-t-md border border-b-0 border-border bg-surface"
              />
            )}

            <div
              className={cn(
                'relative flex items-end gap-2 border border-border bg-surface px-3 py-2 shadow-[0_10px_40px_rgba(0,0,0,0.22)] transition-all duration-200 focus-within:border-primary/50 focus-within:bg-surface-elevated focus-within:shadow-[0_0_0_1px_var(--v-accent-16),0_12px_48px_rgba(0,0,0,0.30)]',
                attachments.length > 0 || referenceCount > 0 ? 'rounded-b-md rounded-t-none' : 'rounded-md',
              )}
              style={{
                background: 'var(--v-panel)',
                borderColor: 'var(--v-border)',
              }}
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
                  disabled={isStreaming || contextLimitReached}
                  className="rounded-md p-1.5 text-foreground-muted transition-colors hover:bg-primary/10 hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
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
                onChange={(event) => {
                  setText(event.target.value);
                  setInputText(event.target.value);
                }}
                onKeyDown={handleKeyDown}
                placeholder={
                  contextLimitReached
                    ? '上下文已达到 256K 限制，请新建对话'
                    : isStreaming
                    ? t('chat.streaming.placeholder')
                    : `${modePlaceholders[activeMode]} (${t('chat.ctrlEnter')})`
                }
                rows={1}
                disabled={isStreaming || polishing || contextLimitReached}
                className="flex-1 resize-none overflow-y-auto bg-transparent py-1 text-sm text-foreground outline-none transition-[height] duration-200 ease-out placeholder:text-foreground-subtle disabled:opacity-50"
                style={{ height: 'auto' }}
              />

              {/* ── Right: expand + polish + mic + send ── */}
              <div className="flex items-center gap-0.5 flex-shrink-0 mb-1">
                {showExpandToggle && (
                  <button
                    type="button"
                    onClick={() => setExpanded((value) => !value)}
                    className="rounded-md p-1 text-foreground-muted transition-colors hover:bg-primary/10 hover:text-primary"
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
                    className="h-7 min-w-7 rounded-md px-1.5 text-sm font-semibold text-foreground-muted transition-colors hover:bg-primary/10 hover:text-primary"
                    title={t('chat.revert')}
                    aria-label={t('chat.revert')}
                  >
                    ↩
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handlePolish}
                    disabled={!text.trim() || isStreaming || contextLimitReached}
                    className={cn(
                      'rounded-md p-1 transition-colors',
                      text.trim() && !isStreaming && !contextLimitReached
                        ? 'text-foreground-muted hover:bg-primary/10 hover:text-primary'
                        : 'cursor-not-allowed text-foreground-subtle',
                    )}
                    title={t('chat.polish')}
                    aria-label={t('chat.polish')}
                  >
                    <Sparkles className="h-4 w-4" />
                  </button>
                )}

                {/* Voice */}
                <button className="rounded-md p-1 text-foreground-muted transition-colors hover:bg-primary/10 hover:text-primary">
                  <Mic className="h-4 w-4" />
                </button>

                {/* Send / Stop */}
                {isStreaming ? (
                  <button
                    type="button"
                    onClick={stopGeneration}
                    className="rounded-md bg-error p-1.5 text-white transition-all duration-150 hover:bg-error/80"
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
                        ? 'bg-primary text-background hover:bg-primary-hover'
                        : 'cursor-not-allowed bg-foreground/10 text-foreground-subtle',
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
