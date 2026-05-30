import { useState } from 'react';
import { cn } from '@/lib/utils';
import { HelpCircle, ShieldAlert, Send, RefreshCw } from 'lucide-react';

export interface InteractionOption {
  id: string;
  label: string;
  description?: string;
}

export interface InteractionPayload {
  interaction_id: string;
  type: 'ask_user_question' | 'request_approval';
  title: string;
  description?: string;
  options: InteractionOption[];
  allow_custom_response?: boolean;
  risk_level?: 'low' | 'medium' | 'high';
  plan?: { id: string; title: string; description?: string; risk?: string }[];
}

interface InteractionCardProps {
  payload: InteractionPayload;
  conversationId: string;
  onRespond: (choice: string, message?: string) => void;
  resolved?: boolean;
  resolvedChoice?: string;
}

const RISK_COLORS: Record<string, string> = { low: 'bg-success/10 text-success border-success/20', medium: 'bg-warning/10 text-warning border-warning/20', high: 'bg-error/10 text-error border-error/20' };

export function InteractionCard({ payload, conversationId, onRespond, resolved, resolvedChoice }: InteractionCardProps) {
  const [customText, setCustomText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const isApproval = payload.type === 'request_approval';

  const handleChoice = async (choiceId: string) => {
    if (choiceId === 'custom') {
      if (!customText.trim()) return;
      setSubmitting(true);
      await onRespond(choiceId, customText.trim());
      return;
    }
    setSubmitting(true);
    await onRespond(choiceId);
  };

  return (
    <div className="rounded-xl border border-border bg-surface mb-2 overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200">
      {/* Header */}
      <div className={cn('flex items-center gap-2 px-4 py-3 border-b border-border', isApproval ? 'bg-warning/5' : 'bg-primary/5')}>
        {isApproval ? <ShieldAlert className="w-4 h-4 text-warning" /> : <HelpCircle className="w-4 h-4 text-primary" />}
        <div>
          <p className="text-xs font-semibold text-foreground">{payload.title}</p>
          {payload.risk_level && (
            <span className={cn('text-[10px] px-1.5 py-0.5 rounded-full border mt-0.5 inline-block', RISK_COLORS[payload.risk_level])}>
              Risk: {payload.risk_level}
            </span>
          )}
        </div>
      </div>

      {/* Description */}
      {payload.description && (
        <p className="px-4 py-2 text-xs text-foreground-muted border-b border-border">{payload.description}</p>
      )}

      {/* Plan (approval only) */}
      {isApproval && payload.plan && payload.plan.length > 0 && (
        <div className="px-4 py-2 border-b border-border space-y-1">
          {payload.plan.map((step) => (
            <div key={step.id} className="flex items-start gap-2 text-xs">
              <span className="text-foreground-subtle mt-0.5">•</span>
              <div>
                <span className="text-foreground">{step.title}</span>
                {step.description && <span className="text-foreground-subtle ml-1">{step.description}</span>}
                {step.risk && (
                  <span className={cn('text-[10px] px-1 py-0 rounded ml-1.5', RISK_COLORS[step.risk])}>{step.risk}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Options */}
      <div className="p-3 space-y-1.5">
        {payload.options.filter(o => o.id !== 'custom').map((opt) => (
          <button
            key={opt.id}
            onClick={() => handleChoice(opt.id)}
            disabled={resolved || submitting}
            className={cn(
              'w-full text-left px-3 py-2 rounded-lg text-xs transition-colors border border-transparent',
              resolved && resolvedChoice === opt.id
                ? 'bg-primary/10 border-primary/20 text-primary font-medium'
                : 'hover:bg-surface-hover text-foreground-muted hover:text-foreground',
              submitting && 'opacity-50 cursor-not-allowed',
            )}
          >
            {opt.label}
            {opt.description && <span className="block text-[10px] text-foreground-subtle mt-0.5">{opt.description}</span>}
          </button>
        ))}

        {/* Custom response input */}
        {payload.allow_custom_response !== false && !resolved && (
          <div className="flex gap-2 pt-1">
            <input
              type="text"
              value={customText}
              onChange={(e) => setCustomText(e.target.value)}
              placeholder="Custom response…"
              className="flex-1 px-3 py-1.5 text-xs rounded-lg bg-background border border-border text-foreground placeholder:text-foreground-subtle focus:outline-none focus:border-primary/50"
              onKeyDown={(e) => { if (e.key === 'Enter' && customText.trim()) handleChoice('custom'); }}
            />
            <button
              onClick={() => handleChoice('custom')}
              disabled={!customText.trim() || submitting}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                customText.trim() && !submitting
                  ? 'bg-primary text-white hover:bg-primary-hover'
                  : 'bg-surface-hover text-foreground-muted cursor-not-allowed',
              )}
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* Resolved state */}
      {resolved && (
        <div className="px-4 py-2 border-t border-border bg-surface-hover/30 flex items-center gap-2 text-[10px] text-foreground-muted">
          <RefreshCw className="w-3 h-3" />
          Awaiting agent response…
        </div>
      )}
    </div>
  );
}
