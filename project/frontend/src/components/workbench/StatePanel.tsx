import type { ElementType, ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Brain,
  CheckCircle,
  Cpu,
  FolderTree,
  GitBranch,
  SlidersHorizontal,
  Wrench,
} from 'lucide-react';
import { cn, formatDuration } from '@/lib/utils';
import { ContextManagerPanel } from '@/components/composer/ContextManagerPanel';
import { WorkspacePanel } from '@/components/workspace/WorkspacePanel';
import { useChatStore } from '@/stores/chatStore';
import { useToolStore } from '@/stores/useToolStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';

type SubTab = 'state' | 'config' | 'workspace';

function MiniStat({
  label,
  value,
  tone = 'neutral',
}: {
  label: string;
  value: string | number;
  tone?: 'neutral' | 'ok' | 'warn' | 'error';
}) {
  const color = tone === 'ok' ? '#5a8a5e' : tone === 'warn' ? '#b8933e' : tone === 'error' ? '#a85450' : '#e8e6e3';
  return (
    <div className="rounded-md border border-white/[0.055] bg-white/[0.03] px-3 py-2">
      <div className="font-mono-code text-[10.5px] tracking-[0.02em] text-[#5c5855]">{label}</div>
      <div className="mt-1 truncate font-mono-code text-[13px] tracking-[0.02em]" style={{ color }}>{value}</div>
    </div>
  );
}

function StateCard({
  icon: Icon,
  title,
  children,
  accent = '#9a9590',
}: {
  icon: ElementType;
  title: string;
  children: ReactNode;
  accent?: string;
}) {
  return (
    <section className="rounded-md border border-white/[0.06] bg-[rgba(20,20,22,0.62)] p-3">
      <div className="mb-2.5 flex items-center gap-2">
        <Icon className="h-4 w-4" style={{ color: accent }} />
        <span className="text-[13px] font-semibold text-[#e8e6e3]">{title}</span>
      </div>
      {children}
    </section>
  );
}

function ContextMeter() {
  const usage = useChatStore((s) => s.contextUsage);
  if (!usage) {
    return (
      <div className="text-[12px] leading-5 text-[#5c5855]">
        暂无上下文统计。发送消息后会自动更新。
      </div>
    );
  }
  const pct = Math.min(100, Math.max(0, usage.usageRatio * 100));
  const color = pct < 60 ? '#5a8a5e' : pct < 86 ? '#b8933e' : '#a85450';
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between font-mono-code text-[11px] text-[#9a9590]">
        <span>{(usage.totalTokens / 1000).toFixed(1)}K / {(usage.maxTokens / 1000).toFixed(0)}K</span>
        <span style={{ color }}>{pct.toFixed(0)}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

function RuntimeState() {
  const {
    messages,
    selectedModelId,
    models,
    isStreaming,
    currentConversationId,
    apiError,
  } = useChatStore();
  const tools = useToolStore((s) => s.tools);
  const syncFromBackend = useToolStore((s) => s.syncFromBackend);
  const { gitStatus, fileTree, loadWorkspace } = useWorkspaceStore();

  useEffect(() => {
    void syncFromBackend();
  }, [syncFromBackend]);

  useEffect(() => {
    void loadWorkspace(currentConversationId);
  }, [currentConversationId, loadWorkspace]);

  const model = models.find((item) => item.id === selectedModelId);
  const enabledTools = tools.filter((tool) => tool.isEnabled);
  const assistantCount = messages.filter((message) => message.role === 'assistant').length;
  const userCount = messages.filter((message) => message.role === 'user').length;
  const latestSegment = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const segments = messages[i].segments ?? [];
      for (let j = segments.length - 1; j >= 0; j -= 1) {
        const segment = segments[j];
        if (segment.type === 'execution') return segment.execution;
      }
    }
    return null;
  }, [messages]);

  return (
    <div className="space-y-2.5 p-3">
      <StateCard icon={Activity} title="Runtime" accent={isStreaming ? '#c66a38' : '#5a8a5e'}>
        <div className="grid grid-cols-2 gap-2">
          <MiniStat label="状态" value={isStreaming ? 'Running' : 'Ready'} tone={isStreaming ? 'warn' : 'ok'} />
          <MiniStat label="消息" value={`${userCount}/${assistantCount}`} />
          <MiniStat label="工具" value={`${enabledTools.length}/${tools.length}`} />
          <MiniStat label="Workspace" value={currentConversationId ? 'Active' : 'None'} tone={currentConversationId ? 'ok' : 'neutral'} />
        </div>
      </StateCard>

      <StateCard icon={Cpu} title="Model" accent="#c66a38">
        <div className="truncate font-mono-code text-[12px] text-[#e8e6e3]">{model?.name ?? selectedModelId}</div>
        <div className="mt-2">
          <ContextMeter />
        </div>
      </StateCard>

      <StateCard icon={Wrench} title="Tools" accent="#9ab2d7">
        <div className="flex flex-wrap gap-1.5">
          {enabledTools.slice(0, 18).map((tool) => (
            <span key={tool.name} className="rounded-md bg-white/[0.04] px-2 py-1 font-mono-code text-[10.5px] text-[#9a9590]">
              {tool.name}
            </span>
          ))}
          {enabledTools.length > 18 && (
            <span className="rounded-md bg-white/[0.04] px-2 py-1 font-mono-code text-[10.5px] text-[#5c5855]">
              +{enabledTools.length - 18}
            </span>
          )}
        </div>
      </StateCard>

      <StateCard icon={FolderTree} title="Workspace" accent="#5a8a5e">
        <div className="grid grid-cols-2 gap-2">
          <MiniStat label="文件" value={fileTree.length} />
          <MiniStat label="Git" value={gitStatus?.is_git_repo ? gitStatus.branch || 'Repo' : 'No repo'} tone={gitStatus?.is_git_repo ? 'ok' : 'neutral'} />
        </div>
        {gitStatus?.is_dirty && (
          <div className="mt-2 flex items-center gap-2 rounded-md bg-white/[0.035] px-2 py-1.5 text-[12px] text-[#9a9590]">
            <GitBranch className="h-3.5 w-3.5 text-[#b8933e]" />
            Working tree has changes.
          </div>
        )}
      </StateCard>

      {latestSegment && (
        <StateCard icon={Brain} title="Latest Segment" accent="#c66a38">
          <div className="space-y-2">
            <div className="truncate text-[12px] text-[#e8e6e3]">
              {latestSegment.summary || latestSegment.goal || latestSegment.title || latestSegment.status}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <MiniStat label="Steps" value={latestSegment.steps.length} />
              <MiniStat label="Time" value={latestSegment.durationMs ? formatDuration(latestSegment.durationMs) : '-'} />
            </div>
          </div>
        </StateCard>
      )}

      {apiError ? (
        <StateCard icon={AlertTriangle} title="Last Error" accent="#a85450">
          <div className="whitespace-pre-wrap break-words font-mono-code text-[11.5px] leading-5 text-[#c97a76]">{apiError}</div>
        </StateCard>
      ) : (
        <StateCard icon={CheckCircle} title="Health" accent="#5a8a5e">
          <div className="text-[12px] text-[#9a9590]">前端、后端与工具管理面板均已接入真实 API。</div>
        </StateCard>
      )}
    </div>
  );
}

/**
 * The diagnostics panel (State / Config / Workspace) — preserved from the
 * previous right panel and now hosted as a pinned tab inside the workbench.
 */
export function StatePanel() {
  const [tab, setTab] = useState<SubTab>('state');
  const currentConversationId = useChatStore((s) => s.currentConversationId);

  const subTabs: Array<{ id: SubTab; label: string; icon: ElementType }> = [
    { id: 'state', label: 'State', icon: Activity },
    { id: 'config', label: 'Config', icon: SlidersHorizontal },
    { id: 'workspace', label: 'Workspace', icon: FolderTree },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-0.5 border-b border-white/[0.06] px-3 py-2">
        {subTabs.map((item) => {
          const Icon = item.icon;
          const active = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={cn(
                'relative flex items-center gap-1.5 rounded-md px-2.5 py-1.5 font-mono-code text-[11.5px] tracking-[0.02em] transition-colors',
                active ? 'text-[#e8e6e3]' : 'text-[#5c5855] hover:text-[#9a9590]',
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {item.label}
              {active && <span className="absolute inset-x-2 bottom-0 h-px rounded-full bg-primary" />}
            </button>
          );
        })}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === 'state' && <RuntimeState />}
        {tab === 'config' && <ContextManagerPanel className="border-0 bg-transparent" />}
        {tab === 'workspace' && <WorkspacePanel currentConversationId={currentConversationId} />}
      </div>
    </div>
  );
}
