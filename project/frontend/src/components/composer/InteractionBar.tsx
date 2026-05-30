import { useState } from 'react';
import { HelpCircle, Send, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chatStore';
import { useI18n } from '@/i18n';

const RISK_STYLE: Record<string, string> = {
  low: 'bg-success/10 text-success border-success/20',
  medium: 'bg-warning/10 text-warning border-warning/20',
  high: 'bg-error/10 text-error border-error/20',
};

const FALLBACK_APPROVAL_OPTIONS = [
  { id: 'approve', label: 'Approve' },
  { id: 'reject_revise', label: 'Reject & Revise' },
  { id: 'reject_exit', label: 'Reject & Exit' },
];

export function InteractionBar({ className }: { className?: string }) {
  const [customText, setCustomText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const pending = useChatStore((state) => state.pendingInteraction);
  const respond = useChatStore((state) => state.respondToInteraction);
  const { t } = useI18n();

  if (!pending) return null;

  const isApproval = pending.type === 'request_approval';
  const Icon = isApproval ? ShieldAlert : HelpCircle;
  const options =
    pending.optionItems?.filter((option) => option.id !== 'custom') ??
    (isApproval ? FALLBACK_APPROVAL_OPTIONS : []);

  const submit = async (choice: string) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await respond(choice, customText.trim() || undefined);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className={cn(
        'mb-2 overflow-hidden rounded-xl border border-border bg-surface shadow-sm animate-in fade-in slide-in-from-bottom-2 duration-200',
        className,
      )}
    >
      <div
        className={cn(
          'flex items-start gap-2 border-b border-border px-4 py-2.5',
          isApproval ? 'bg-warning/5' : 'bg-primary/5',
        )}
      >
        <Icon className={cn('mt-0.5 h-4 w-4', isApproval ? 'text-warning' : 'text-primary')} />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-foreground">
            {pending.title || (isApproval ? 'Approval required' : 'Response required')}
          </p>
          {pending.message && (
            <p className="mt-1 text-xs leading-relaxed text-foreground-muted">
              {pending.message}
            </p>
          )}
          {isApproval && pending.riskLevel && (
            <span
              className={cn(
                'mt-2 inline-block rounded-full border px-1.5 py-0.5 text-[10px]',
                RISK_STYLE[pending.riskLevel],
              )}
            >
              {pending.riskLevel}
            </span>
          )}
        </div>
      </div>

      {isApproval && pending.plan && pending.plan.length > 0 && (
        <div className="space-y-1 border-b border-border px-4 py-2">
          {pending.plan.map((step) => (
            <div key={step.id} className="flex items-start gap-2 text-xs">
              <span className="mt-0.5 text-foreground-subtle">-</span>
              <div className="min-w-0">
                <span className="text-foreground">{step.title}</span>
                {step.description && (
                  <span className="ml-1 text-foreground-subtle">{step.description}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-2 p-3">
        {options.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {options.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => submit(option.id)}
                disabled={submitting}
                className={cn(
                  'rounded-lg border border-border px-3 py-1.5 text-xs transition-colors disabled:opacity-50',
                  'text-foreground-muted hover:border-primary/30 hover:bg-surface-hover hover:text-foreground',
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        )}

        {pending.allowCustom !== false && (
          <div className="flex gap-2">
            <input
              type="text"
              value={customText}
              onChange={(event) => setCustomText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && customText.trim()) {
                  event.preventDefault();
                  void submit('custom');
                }
              }}
              placeholder={t('chat.customResponse')}
              disabled={submitting}
              className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground-subtle focus:border-primary/50 focus:outline-none disabled:opacity-50"
            />
            <button
              type="button"
              onClick={() => submit('custom')}
              disabled={!customText.trim() || submitting}
              className={cn(
                'rounded-lg px-3 py-2 transition-colors',
                customText.trim() && !submitting
                  ? 'bg-primary text-white hover:bg-primary-hover'
                  : 'cursor-not-allowed bg-surface-hover text-foreground-muted',
              )}
              aria-label={t('chat.send')}
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
