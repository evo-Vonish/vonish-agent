import { useState, useRef, useEffect } from 'react';
import { FolderOpen, ChevronDown, Check, Plus, FolderX } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useI18n } from '@/i18n';
import { useSessionDraftStore } from '@/stores/sessionDraftStore';
import { useChatStore } from '@/stores/chatStore';
import { listProjects } from '@/services/api';
import type { ProjectSummary } from '@/types';

const BG = '#252423';
const BORDER = '1px solid rgba(255,255,255,0.07)';
const SHADOW = '0 12px 40px rgba(0,0,0,0.50)';
const T1 = '#e2e0dd';
const T2 = '#a6a4a1';
const TM = '#6f6d6b';
const HOVER = 'rgba(255,255,255,0.05)';
const ACTIVE = 'rgba(255,255,255,0.04)';
const DIV = 'rgba(255,255,255,0.06)';
const BLUE = '#4a90d9';

// ═══════════════════════════════════════════
//  Workspace Selector – only shown before conversation starts
// ═══════════════════════════════════════════
export function SessionOptionsRow() {
  const { t } = useI18n();
  const { workspaceId, setWorkspaceId } = useSessionDraftStore();
  const messages = useChatStore((s) => s.messages);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onMouse = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node) &&
          btnRef.current && !btnRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onMouse);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onMouse);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  useEffect(() => {
    void listProjects().then(setProjects).catch(() => setProjects([]));
  }, []);

  // Hide when conversation has started
  if (messages.length > 0) return null;

  const selected = projects.find((item) => item.id === workspaceId);
  const label = selected?.name ?? workspaceId ?? t('session.workspace.noProject');

  const addProject = async () => {
    const name = window.prompt(t('session.workspace.addProject'));
    const trimmed = name?.trim();
    if (!trimmed) return;
    const id = trimmed;
    setWorkspaceId(id);
    setProjects((items) => [{ id, name: trimmed, conversationCount: 0 }, ...items]);
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        ref={btnRef}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'flex items-center gap-1 px-2 py-1 rounded-md text-[11px] transition-colors',
          open ? 'text-foreground bg-surface-hover' : 'text-foreground-muted hover:text-foreground hover:bg-surface-hover',
        )}
      >
        <FolderOpen className="w-3.5 h-3.5 flex-shrink-0" />
        <span className="max-w-[120px] truncate">{label}</span>
        <ChevronDown className={cn('w-3 h-3 transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div ref={panelRef}
          className="absolute left-0 bottom-full mb-1.5 z-50 w-48 animate-in fade-in slide-in-from-bottom-1 duration-150"
          style={{ background: BG, border: BORDER, borderRadius: 12, boxShadow: SHADOW, padding: 6 }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* search placeholder */}
          <div className="flex items-center gap-1.5 px-2 h-7 rounded-md mb-0.5 text-[11px]"
            style={{ background: 'rgba(255,255,255,0.04)', color: TM }}>
            <SearchSm className="w-3 h-3 flex-shrink-0" />
            {t('session.workspace.searchProjects')}
          </div>

          {projects.map((project) => {
            const active = workspaceId === project.id;
            return (
              <button key={project.id}
                onClick={() => { setWorkspaceId(project.id); setOpen(false); }}
                className="w-full flex items-center gap-2.5 px-3 h-[36px] rounded-[9px] text-[13px] cursor-pointer text-left transition-colors"
                style={{ color: active ? T1 : T2, background: active ? ACTIVE : 'transparent' }}
                onMouseEnter={(e) => { e.currentTarget.style.background = HOVER; e.currentTarget.style.color = T1; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = active ? ACTIVE : 'transparent'; e.currentTarget.style.color = active ? T1 : T2; }}
              >
                <span className="flex-1 truncate">{project.name || project.id}</span>
                <span className="text-[10px]" style={{ color: TM }}>{project.conversationCount}</span>
                {active && <Check className="w-3.5 h-3.5 flex-shrink-0" style={{ color: BLUE }} />}
              </button>
            );
          })}

          <div className="mx-3 my-1 border-t" style={{ borderColor: DIV }} />

          <button
            onClick={() => { void addProject(); }}
            className="w-full flex items-center gap-2.5 px-3 h-[36px] rounded-[9px] text-[13px] cursor-pointer transition-colors"
            style={{ color: T2, background: 'transparent' }}
            onMouseEnter={(e) => { e.currentTarget.style.background = HOVER; e.currentTarget.style.color = T1; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = T2; }}
          >
            <Plus className="w-4 h-4 flex-shrink-0" style={{ color: '#9d9b98' }} />
            <span className="flex-1">{t('session.workspace.addProject')}</span>
          </button>

          <button
            onClick={() => { setWorkspaceId(null); setOpen(false); }}
            className="w-full flex items-center gap-2.5 px-3 h-[36px] rounded-[9px] text-[13px] cursor-pointer transition-colors"
            style={{ color: workspaceId === null ? T1 : T2, background: workspaceId === null ? ACTIVE : 'transparent' }}
            onMouseEnter={(e) => { e.currentTarget.style.background = HOVER; e.currentTarget.style.color = T1; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = workspaceId === null ? ACTIVE : 'transparent'; e.currentTarget.style.color = workspaceId === null ? T1 : T2; }}
          >
            <FolderX className="w-4 h-4 flex-shrink-0" style={{ color: '#9d9b98' }} />
            <span className="flex-1">{t('session.workspace.noProject')}</span>
            {workspaceId === null && <Check className="w-3.5 h-3.5 flex-shrink-0" style={{ color: BLUE }} />}
          </button>
        </div>
      )}
    </div>
  );
}

function SearchSm({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
    </svg>
  );
}
