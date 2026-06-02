import { useState, useRef, useEffect } from 'react';
import { Settings2, Cpu, Gauge, ListTodo, Shield, ChevronRight, Check, Lock, Unlock, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useI18n } from '@/i18n';
import { useChatStore } from '@/stores/chatStore';
import { useSessionDraftStore } from '@/stores/sessionDraftStore';
import type { PermissionDraftMode, DirectoryAccessDraftMode } from '@/types';
import { latestTodoFromMessages } from '@/lib/todo';

// ── Codex dark panel tokens ──
const BG = '#252423';
const BORDER = '1px solid rgba(255,255,255,0.07)';
const SHADOW = '0 12px 40px rgba(0,0,0,0.50)';
const T1 = '#e2e0dd';
const T2 = '#a6a4a1';
const TM = '#6f6d6b';
const HOVER = 'rgba(255,255,255,0.05)';
const ACTIVE = 'rgba(255,255,255,0.04)';
const DIV = 'rgba(255,255,255,0.06)';
const IC = '#9d9b98';
const BLUE = '#4a90d9';

// ═══════════════════════════════════════════
//  Shared primitives
// ═══════════════════════════════════════════
function usePopover(open: boolean, btnRef: React.RefObject<HTMLElement | null>, panelRef: React.RefObject<HTMLElement | null>, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const onMouse = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node) &&
          btnRef.current && !btnRef.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('mousedown', onMouse);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onMouse);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, onClose, btnRef, panelRef]);
}

function itemStyle(active?: boolean): React.CSSProperties {
  return {
    color: active ? T1 : T2,
    background: active ? ACTIVE : 'transparent',
    display: 'flex', alignItems: 'center', gap: 10,
    width: '100%', padding: '0 12px', height: 36,
    borderRadius: 9, fontSize: 13, cursor: 'pointer',
    transition: 'background 0.15s, color 0.15s',
  };
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="px-3 pt-2 pb-0.5 text-[10px] font-semibold uppercase tracking-wide" style={{ color: TM }}>{children}</p>;
}

// ═══════════════════════════════════════════
//  Sub-panels
// ═══════════════════════════════════════════

/** Model sub-panel */
function ModelSub({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const { models, selectedModelId, setSelectedModel } = useChatStore();

  return (
    <div className="w-52" style={{ background: BG, border: BORDER, borderRadius: 14, boxShadow: SHADOW, padding: 6 }}>
      <SectionLabel>{t('model.selector')}</SectionLabel>
      {models.map((m) => {
        const active = m.id === selectedModelId;
        return (
          <button key={m.id} style={itemStyle(active)}
            onClick={() => { setSelectedModel(m.id); onClose(); }}
            onMouseEnter={(e) => { e.currentTarget.style.background = HOVER; e.currentTarget.style.color = T1; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = active ? ACTIVE : 'transparent'; e.currentTarget.style.color = active ? T1 : T2; }}
          >
            <Cpu className="w-4 h-4 flex-shrink-0" style={{ color: IC }} />
            <span className="flex-1 text-left truncate">{m.name}</span>
            {active && <Check className="w-3.5 h-3.5 flex-shrink-0" style={{ color: BLUE }} />}
          </button>
        );
      })}
    </div>
  );
}

/** Ring gauge – from ContextManagerPanel */
function TokenGauge({ used, budget }: { used: number; budget: number }) {
  const pct = Math.min(100, (used / budget) * 100);
  const radius = 34;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;
  const color = pct < 50 ? '#22c55e' : pct < 80 ? '#f59e0b' : '#ef4444';

  return (
    <div className="flex flex-col items-center py-2">
      <div className="relative w-[88px] h-[88px]">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r={radius} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="7" />
          <circle cx="50" cy="50" r={radius} fill="none" stroke={color} strokeWidth="7"
            strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
            className="transition-all duration-700 ease-out" />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-[15px] font-bold" style={{ color: T1 }}>{pct.toFixed(0)}%</span>
          <span className="text-[10px]" style={{ color: TM }}>已使用</span>
        </div>
      </div>
      <div className="text-center mt-1">
        <span className="text-[11px]" style={{ color: T2 }}>
          {(used / 1000).toFixed(1)}K / {(budget / 1000).toFixed(0)}K tokens
        </span>
      </div>
    </div>
  );
}

/** Context sub-panel — ring gauge + stats + profile + compression */
function ContextSub({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const usage = useChatStore((s) => s.contextUsage);
  const contextProfile = useChatStore((s) => s.contextProfile);
  const fetchContextUsage = useChatStore((s) => s.fetchContextUsage);
  const switchContextProfile = useChatStore((s) => s.switchContextProfile);
  const [loading, setLoading] = useState(false);

  const hasData = usage !== null;
  const used = usage?.totalTokens ?? 0;
  const max = usage?.maxTokens ?? 0;

  const handleRefresh = async () => {
    setLoading(true);
    await fetchContextUsage();
    setLoading(false);
  };

  const handleSwitchProfile = async (id: string) => {
    const cid = useChatStore.getState().currentConversationId;
    if (!cid) return;
    switchContextProfile(id);
    try {
      await fetch(`/api/context/${cid}/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: id }),
      });
    } catch {}
    await fetchContextUsage();
  };

  const handleCompact = async (level: string) => {
    const state = useChatStore.getState();
    const cid = state.currentConversationId;
    if (!cid) return;
    setLoading(true);
    try {
      await fetch(`/api/context/${cid}/compact?level=${level}&profile_name=${state.contextProfile.id}&model_id=${state.selectedModelId}`, { method: 'POST' });
    } catch {}
    await fetchContextUsage();
    setLoading(false);
  };

  const compressionLevels = [
    { value: 'none', label: '无' },
    { value: 'light', label: '轻度' },
    { value: 'medium', label: '中度' },
    { value: 'aggressive', label: '激进' },
  ];

  const profiles = useChatStore.getState().availableProfiles;

  return (
    <div className="w-60" style={{ background: BG, border: BORDER, borderRadius: 14, boxShadow: SHADOW, padding: 6 }}>
      <div className="flex items-center justify-between px-2 pt-1 pb-0.5">
        <SectionLabel>{t('context.title')}</SectionLabel>
        <button
          onClick={handleRefresh}
          disabled={loading}
          className="p-1 rounded hover:bg-white/5 text-foreground-muted disabled:opacity-40 transition-colors"
        >
          <RefreshCw className={cn('w-3 h-3', loading && 'animate-spin')} style={{ color: IC }} />
        </button>
      </div>

      {hasData ? (
        <>
          <TokenGauge used={used} budget={max} />

          <div className="mx-3 border-t" style={{ borderColor: DIV }} />

          {/* Stats */}
          <div className="px-2 py-2 space-y-0.5">
            {[
              [t('context.rounds'), usage?.userMessageCount ?? 0],
              [t('context.toolCalls'), usage?.toolCallCount ?? 0],
              [t('context.files'), usage?.workspaceFileCount ?? 0],
              [t('context.memory'), usage?.memoryItemCount ?? 0],
            ].map(([label, value]) => (
              <div key={label} className="flex items-center justify-between px-2 h-7 rounded-md text-[12px]" style={{ color: T2 }}>
                <span>{label}</span>
                <span style={{ color: T1 }}>{value}</span>
              </div>
            ))}

            {/* Components breakdown */}
            {usage?.components && (
              <>
                <div className="mx-2 border-t my-1" style={{ borderColor: DIV }} />
                <div className="space-y-1">
                  {Object.entries(usage.components).map(([key, value]) => {
                    const labelMap: Record<string, string> = {
                      system_prompt: 'System',
                      recent_messages: 'Messages',
                      tool_results: 'Tools',
                      current_query: 'Query',
                    };
                    const cp = max > 0 ? (value / max) * 100 : 0;
                    return (
                      <div key={key} className="flex items-center gap-2 text-[10px] px-2">
                        <span className="w-14 truncate" style={{ color: TM }}>{labelMap[key] ?? key}</span>
                        <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
                          <div className="h-full rounded-full bg-primary/50" style={{ width: `${Math.min(100, cp)}%` }} />
                        </div>
                        <span className="w-8 text-right tabular-nums" style={{ color: T1 }}>{value >= 1000 ? `${(value / 1000).toFixed(0)}K` : value}</span>
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            <div className="mx-2 border-t my-1" style={{ borderColor: DIV }} />

            {/* Profile switcher */}
            <div>
              <div className="text-[10px] mb-1 px-2" style={{ color: TM }}>{t('context.profile')}</div>
              <div className="grid grid-cols-3 gap-1 px-1">
                {profiles.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => handleSwitchProfile(p.id)}
                    className="rounded-md border px-1 py-0.5 text-[10px] transition-colors"
                    style={{
                      borderColor: (usage?.profile ?? contextProfile.id) === p.id ? 'rgba(74,144,217,0.4)' : 'rgba(255,255,255,0.08)',
                      background: (usage?.profile ?? contextProfile.id) === p.id ? 'rgba(74,144,217,0.12)' : 'transparent',
                      color: (usage?.profile ?? contextProfile.id) === p.id ? BLUE : T2,
                    }}
                  >
                    {p.name}
                  </button>
                ))}
              </div>
            </div>

            {/* Compression levels */}
            <div className="mt-1">
              <div className="text-[10px] mb-1 px-2" style={{ color: TM }}>{t('context.compression')}</div>
              <div className="grid grid-cols-2 gap-1 px-1">
                {compressionLevels.map((level) => (
                  <button
                    key={level.value}
                    onClick={() => handleCompact(level.value)}
                    className="rounded-md border px-2 py-0.5 text-[10px] transition-colors"
                    style={{
                      borderColor: contextProfile.compressionLevel === level.value ? 'rgba(74,144,217,0.4)' : 'rgba(255,255,255,0.08)',
                      background: contextProfile.compressionLevel === level.value ? 'rgba(74,144,217,0.12)' : 'transparent',
                      color: contextProfile.compressionLevel === level.value ? BLUE : T2,
                    }}
                  >
                    {level.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="py-8 text-center text-[12px]" style={{ color: TM }}>
          {loading ? '加载中…' : '—'}
        </div>
      )}
    </div>
  );
}

/** Task sub-panel */
function TaskSub({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const messages = useChatStore((s) => s.messages);
  const todo = latestTodoFromMessages(messages);
  const total = todo?.items?.length ?? 0;
  const done = (todo?.items ?? []).filter((it) => it.status === 'done' || it.status === 'cancelled').length;

  return (
    <div className="w-52" style={{ background: BG, border: BORDER, borderRadius: 14, boxShadow: SHADOW, padding: 6 }}>
      <SectionLabel>{t('todo.title')}</SectionLabel>
      <div className="px-3 py-2 space-y-1">
        {total > 0 ? (
          <>
            <div className="flex items-center justify-between text-[12px]" style={{ color: T2 }}>
              <span>{t('todo.title')}</span>
              <span style={{ color: T1 }}>{done}/{total}</span>
            </div>
            <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.08)' }}>
              <div className="h-full rounded-full bg-success transition-all" style={{ width: `${(done / total) * 100}%` }} />
            </div>
          </>
        ) : (
          <p className="text-[12px]" style={{ color: TM }}>{t('todo.noItems')}</p>
        )}
      </div>
    </div>
  );
}

/** Permission sub-panel — audit mode + directory access */
const PERMS: { mode: PermissionDraftMode; key: string }[] = [
  { mode: 'default', key: 'session.permission.default' },
  { mode: 'auto_review', key: 'session.permission.autoReview' },
  { mode: 'full_access', key: 'session.permission.full' },
];
const DIRS: { mode: DirectoryAccessDraftMode; key: string }[] = [
  { mode: 'locked_workspace', key: 'session.directoryAccess.locked' },
  { mode: 'request_external', key: 'session.directoryAccess.external' },
];

function PermissionSub({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const { permissionMode, setPermissionMode, directoryAccessMode, setDirectoryAccessMode } = useSessionDraftStore();

  return (
    <div className="w-52" style={{ background: BG, border: BORDER, borderRadius: 14, boxShadow: SHADOW, padding: 6 }}>
      <SectionLabel>{t('session.permission.audit')}</SectionLabel>
      {PERMS.map(({ mode, key }) => {
        const active = mode === permissionMode;
        return (
          <button key={mode} style={itemStyle(active)}
            onClick={() => { setPermissionMode(mode); onClose(); }}
            onMouseEnter={(e) => { e.currentTarget.style.background = HOVER; e.currentTarget.style.color = T1; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = active ? ACTIVE : 'transparent'; e.currentTarget.style.color = active ? T1 : T2; }}
          >
            <Shield className="w-4 h-4 flex-shrink-0" style={{ color: IC }} />
            <span className="flex-1">{t(key)}</span>
            {active && <Check className="w-3.5 h-3.5 flex-shrink-0" style={{ color: BLUE }} />}
          </button>
        );
      })}

      <div className="mx-3 my-1 border-t" style={{ borderColor: DIV }} />

      <SectionLabel>{t('session.directoryAccess')}</SectionLabel>
      {DIRS.map(({ mode, key }) => {
        const active = mode === directoryAccessMode;
        const Icon = mode === 'locked_workspace' ? Lock : Unlock;
        return (
          <button key={mode} style={itemStyle(active)}
            onClick={() => { setDirectoryAccessMode(mode); onClose(); }}
            onMouseEnter={(e) => { e.currentTarget.style.background = HOVER; e.currentTarget.style.color = T1; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = active ? ACTIVE : 'transparent'; e.currentTarget.style.color = active ? T1 : T2; }}
          >
            <Icon className="w-4 h-4 flex-shrink-0" style={{ color: IC }} />
            <span className="flex-1">{t(key)}</span>
            {active && <Check className="w-3.5 h-3.5 flex-shrink-0" style={{ color: BLUE }} />}
          </button>
        );
      })}
    </div>
  );
}

// ═══════════════════════════════════════════
//  ConfigPanel — main button + popover + sub-panels
// ═══════════════════════════════════════════
type SubPanelKey = 'model' | 'context' | 'task' | 'permission' | null;

export function ConfigPanel({ className }: { className?: string }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [sub, setSub] = useState<SubPanelKey>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  usePopover(open, btnRef, panelRef, () => { setOpen(false); setSub(null); });

  const model = useChatStore((s) => s.models.find((m) => m.id === s.selectedModelId));
  const usage = useChatStore((s) => s.contextUsage);
  const { permissionMode } = useSessionDraftStore();
  const permLabel = t(`session.permission.${permissionMode === 'full_access' ? 'full' : permissionMode === 'auto_review' ? 'autoReview' : 'default'}`);

  const closeAll = () => { setOpen(false); setSub(null); };

  // ── Main panel items ──
  const items: { key: SubPanelKey; icon: React.ElementType; label: string; right: string }[] = [
    { key: 'model', icon: Cpu, label: t('model.selector'), right: model?.name ?? t('model.default') },
    { key: 'context', icon: Gauge, label: t('context.title'), right: usage ? `${(usage.totalTokens / 1000).toFixed(1)}K / ${(usage.maxTokens / 1000).toFixed(0)}K` : '—' },
    { key: 'task', icon: ListTodo, label: t('todo.title'), right: '—' },
    { key: 'permission', icon: Shield, label: t('session.permission.audit'), right: permLabel },
  ];

  return (
    <div className={cn('relative', className)}>
      {/* Trigger button */}
      <button
        ref={btnRef}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'flex items-center gap-1 px-2 py-1 rounded-md text-[11px] transition-colors',
          open ? 'text-foreground bg-surface-hover' : 'text-foreground-muted hover:text-foreground hover:bg-surface-hover',
        )}
      >
        <Settings2 className="w-3.5 h-3.5" />
      </button>

      {open && (
        <div
          ref={panelRef}
          className="absolute left-0 bottom-[calc(100%+8px)] z-50 flex"
          style={{ alignItems: 'flex-end' }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Main panel */}
          <div className="flex-shrink-0 w-52 animate-in fade-in slide-in-from-bottom-1 duration-150"
            style={{ background: BG, border: BORDER, borderRadius: 14, boxShadow: SHADOW, padding: 6 }}>
            {items.map(({ key, icon: Icon, label, right }) => (
              <button key={key} style={itemStyle(sub === key)}
                onClick={() => setSub(sub === key ? null : key)}
                onMouseEnter={(e) => { e.currentTarget.style.background = HOVER; e.currentTarget.style.color = T1; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = sub === key ? ACTIVE : 'transparent'; e.currentTarget.style.color = sub === key ? T1 : T2; }}
              >
                <Icon className="w-4 h-4 flex-shrink-0" style={{ color: IC }} />
                <span className="flex-1 text-left truncate">{label}</span>
                <span className="text-[11px] flex items-center gap-0.5 flex-shrink-0" style={{ color: TM }}>
                  <span className="truncate max-w-[90px]">{right}</span>
                  <ChevronRight className="w-3 h-3 flex-shrink-0" />
                </span>
              </button>
            ))}
          </div>

          {/* Sub-panel to the right */}
          {sub && (
            <div className="flex-shrink-0 ml-1.5 animate-in fade-in slide-in-from-left-1 duration-150">
              {sub === 'model' && <ModelSub onClose={closeAll} />}
              {sub === 'context' && <ContextSub onClose={closeAll} />}
              {sub === 'task' && <TaskSub onClose={closeAll} />}
              {sub === 'permission' && <PermissionSub onClose={closeAll} />}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
