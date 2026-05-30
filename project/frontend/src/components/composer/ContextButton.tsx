import { useState, useRef, useEffect } from 'react';
import { Gauge, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chatStore';
import { useI18n } from '@/i18n';
import {
  getContextUsage as fetchContextUsageApi,
  switchContextProfile as switchProfileApi,
  compactContext as compactContextApi,
} from '@/services/api';

function TokenGauge({ used, budget }: { used: number; budget: number }) {
  const pct = Math.min(100, (used / budget) * 100);
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;
  const color = pct < 50 ? '#22c55e' : pct < 80 ? '#f59e0b' : '#ef4444';

  return (
    <div className="flex flex-col items-center py-2">
      <div className="relative w-24 h-24">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r={radius} fill="none" stroke="#2a2a2a" strokeWidth="7" />
          <circle
            cx="50" cy="50" r={radius}
            fill="none" stroke={color} strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="transition-all duration-700 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-base font-bold text-foreground">{Math.round(pct)}%</span>
          <span className="text-[10px] text-foreground-subtle">
            {used >= 1000 ? `${(used / 1000).toFixed(1)}K` : used}
          </span>
        </div>
      </div>
    </div>
  );
}

export function ContextButton({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { t } = useI18n();
  const contextUsage = useChatStore((s) => s.contextUsage);
  const contextProfile = useChatStore((s) => s.contextProfile);
  const fetchContextUsage = useChatStore((s) => s.fetchContextUsage);

  const used = contextUsage?.totalTokens ?? contextProfile.tokenUsed;
  const budget = contextUsage?.maxTokens ?? contextProfile.tokenBudget;
  const pct = budget > 0 ? Math.round((used / budget) * 100) : 0;

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  // Fetch on open
  useEffect(() => {
    if (open) void fetchContextUsage();
  }, [open, fetchContextUsage]);

  const colorClass = pct < 50 ? 'text-success' : pct < 80 ? 'text-warning' : 'text-error';

  const handleRefresh = async () => {
    setLoading(true);
    await fetchContextUsage();
    setLoading(false);
  };

  const handleSwitchProfile = async (id: string) => {
    const cid = useChatStore.getState().currentConversationId;
    if (!cid) return;
    useChatStore.getState().switchContextProfile(id);
    try { await switchProfileApi(cid, id); } catch {}
    await fetchContextUsage();
  };

  const handleCompact = async (level: string) => {
    const cid = useChatStore.getState().currentConversationId;
    if (!cid) return;
    try { await compactContextApi(cid, level); } catch {}
    await fetchContextUsage();
  };

  const compressionLevels = [
    { value: 'none', label: '无压缩' },
    { value: 'light', label: '轻度' },
    { value: 'medium', label: '中度' },
    { value: 'aggressive', label: '激进' },
  ];

  const components = [
    ['System Prompt', 'system_prompt'],
    ['Recent Messages', 'recent_messages'],
    ['Tool Results', 'tool_results'],
    ['Current Query', 'current_query'],
  ] as const;

  return (
    <div ref={ref} className={cn('relative', className)}>
      {/* Trigger button — compact bar */}
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs transition-colors',
          open
            ? 'bg-surface-hover text-foreground'
            : 'text-foreground-muted hover:text-foreground hover:bg-surface-hover'
        )}
        title={t('context.title')}
      >
        <Gauge className={cn('w-3.5 h-3.5', colorClass)} />
        <span className="tabular-nums">{pct}%</span>
        <span className="text-[10px] text-foreground-subtle ml-0.5">
          {(used / 1000).toFixed(1)}K / {(budget / 1000).toFixed(0)}K
        </span>
      </button>

      {/* Popover */}
      {open && (
        <div className="absolute left-0 top-full mt-2 w-72 bg-surface-elevated border border-border rounded-xl shadow-2xl z-50 animate-in fade-in slide-in-from-top-1 duration-150 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-border">
            <span className="text-xs font-semibold text-foreground">{t('context.title')}</span>
            <button
              onClick={handleRefresh}
              disabled={loading}
              className="p-1 rounded hover:bg-surface-hover text-foreground-muted disabled:opacity-50"
            >
              <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
            </button>
          </div>

          <div className="p-3 space-y-3 max-h-[60vh] overflow-y-auto">
            {/* Gauge */}
            <TokenGauge used={used} budget={budget} />

            {/* Stats row */}
            <div className="grid grid-cols-2 gap-1.5">
              <div className="rounded-md border border-border bg-background px-2 py-1.5">
                <div className="text-[10px] text-foreground-subtle">{t('context.rounds')}</div>
                <div className="text-xs font-semibold">{contextUsage?.userMessageCount ?? '—'}</div>
              </div>
              <div className="rounded-md border border-border bg-background px-2 py-1.5">
                <div className="text-[10px] text-foreground-subtle">{t('context.toolCalls')}</div>
                <div className="text-xs font-semibold">{contextUsage?.toolCallCount ?? '—'}</div>
              </div>
              <div className="rounded-md border border-border bg-background px-2 py-1.5">
                <div className="text-[10px] text-foreground-subtle">{t('context.files')}</div>
                <div className="text-xs font-semibold">{contextUsage?.workspaceFileCount ?? '—'}</div>
              </div>
              <div className="rounded-md border border-border bg-background px-2 py-1.5">
                <div className="text-[10px] text-foreground-subtle">{t('context.memory')}</div>
                <div className="text-xs font-semibold">{contextUsage?.memoryItemCount ?? '—'}</div>
              </div>
            </div>

            {/* Profile switcher */}
            <div>
              <h4 className="text-[10px] font-medium text-foreground-muted mb-1.5">{t('context.profile')}</h4>
              <div className="grid grid-cols-3 gap-1">
                {useChatStore.getState().availableProfiles.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => handleSwitchProfile(p.id)}
                    className={cn(
                      'rounded-md border px-1.5 py-1 text-[10px] transition-colors',
                      (contextUsage?.profile ?? contextProfile.id) === p.id
                        ? 'border-primary/50 bg-primary/10 text-primary'
                        : 'border-border text-foreground-muted hover:bg-surface-hover'
                    )}
                  >
                    {p.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Components breakdown */}
            {contextUsage && (
              <div>
                <h4 className="text-[10px] font-medium text-foreground-muted mb-1.5">{t('context.components')}</h4>
                <div className="space-y-1">
                  {components.map(([label, key]) => {
                    const v = contextUsage.components?.[key] ?? 0;
                    const cp = budget > 0 ? (v / budget) * 100 : 0;
                    return (
                      <div key={key} className="flex items-center gap-2 text-[10px]">
                        <span className="text-foreground-muted w-20 truncate">{label}</span>
                        <div className="flex-1 h-1 rounded-full bg-border overflow-hidden">
                          <div className="h-full rounded-full bg-primary/50" style={{ width: `${Math.min(100, cp)}%` }} />
                        </div>
                        <span className="text-foreground font-medium tabular-nums w-8 text-right">{v >= 1000 ? `${(v / 1000).toFixed(0)}K` : v}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Compression */}
            <div>
              <h4 className="text-[10px] font-medium text-foreground-muted mb-1.5">{t('context.compression')}</h4>
              <div className="grid grid-cols-2 gap-1">
                {compressionLevels.map((level) => (
                  <button
                    key={level.value}
                    onClick={() => handleCompact(level.value)}
                    className={cn(
                      'rounded-md border px-2 py-1 text-[10px] transition-colors',
                      contextProfile.compressionLevel === level.value
                        ? 'border-primary/50 bg-primary/10 text-primary'
                        : 'border-border text-foreground-muted hover:bg-surface-hover'
                    )}
                  >
                    {level.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
