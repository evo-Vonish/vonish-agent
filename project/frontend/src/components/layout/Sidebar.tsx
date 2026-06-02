import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  Folder,
  FolderPlus,
  MessageSquare,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';
import { useSessionDraftStore } from '@/stores/sessionDraftStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useI18n } from '@/i18n';
import type { Conversation } from '@/types';
import { formatTime } from '@/lib/utils';
import { Tooltip } from '@/components/ui/Tooltip';
import {
  exportConversation,
  searchConversations,
  type ConversationSearchResult,
  type ExportConversationOptions,
} from '@/services/api';
import { WorkspacePanel } from '@/components/workspace/WorkspacePanel';

interface SidebarProps {
  className?: string;
}

const defaultExportOptions = (title = ''): ExportConversationOptions => ({
  format: 'html',
  anonymize: true,
  includeBasicInfo: true,
  includeModelName: true,
  modelNameMode: 'generic',
  customModelName: '',
  includeUserMessages: true,
  includeAssistantMessages: true,
  includeFinalText: true,
  includeThinking: false,
  includeExecution: true,
  includeToolCalls: true,
  includeToolPayload: false,
  includeToolResult: true,
  includeToolErrors: true,
  includeAttachments: true,
  includeWorkspace: false,
  includeSystemEvents: true,
  customTitle: title,
});

function HighlightSnippet({ snippet, ranges }: { snippet: string; ranges: [number, number][] }) {
  if (!ranges.length) return <>{snippet}</>;
  const parts: React.ReactNode[] = [];
  let last = 0;
  ranges.forEach(([start, end], i) => {
    if (start > last) parts.push(<span key={`t-${i}`}>{snippet.slice(last, start)}</span>);
    parts.push(
      <mark key={`m-${i}`} className="rounded bg-primary/20 px-0.5 text-primary">
        {snippet.slice(start, end)}
      </mark>,
    );
    last = end;
  });
  if (last < snippet.length) parts.push(<span key="tail">{snippet.slice(last)}</span>);
  return <>{parts}</>;
}

function SectionHeader({
  icon,
  title,
  count,
  expanded,
  onToggle,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  count?: number;
  expanded: boolean;
  onToggle: () => void;
  action?: React.ReactNode;
}) {
  return (
    <div className="group flex h-8 items-center gap-1 px-2">
      <button
        type="button"
        onClick={onToggle}
        className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-1.5 py-1 text-left text-[12px] font-medium text-foreground-muted transition-colors hover:text-foreground"
      >
        <span className="grid h-4 w-4 place-items-center text-foreground-subtle">
          {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </span>
        <span className="grid h-4 w-4 place-items-center">{icon}</span>
        <span className="min-w-0 flex-1 truncate">{title}</span>
        {count !== undefined && <span className="text-[11px] text-foreground-subtle">{count}</span>}
      </button>
      {action}
    </div>
  );
}

function SidebarIconButton({
  title,
  onClick,
  children,
  danger,
}: {
  title: string;
  onClick: (event: React.MouseEvent) => void;
  children: React.ReactNode;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={cn(
        'grid h-6 w-6 place-items-center rounded-md text-foreground-subtle opacity-0 transition-all hover:bg-white/[0.07] group-hover:opacity-100',
        danger ? 'hover:text-error' : 'hover:text-foreground',
      )}
    >
      {children}
    </button>
  );
}

function ConversationRow({
  conversation,
  active,
  searchResult,
  nested = false,
  onSelect,
  onExport,
  onDelete,
}: {
  conversation: Conversation;
  active: boolean;
  searchResult?: ConversationSearchResult;
  nested?: boolean;
  onSelect: () => void;
  onExport: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => event.key === 'Enter' && onSelect()}
      className={cn(
        'group flex min-h-9 cursor-pointer items-start gap-2 rounded-xl px-2 py-2 text-left transition-colors',
        nested ? 'ml-8' : 'ml-0',
        active
          ? 'bg-white/[0.075] text-foreground shadow-[inset_0_0_0_1px_rgba(255,255,255,0.04)]'
          : 'text-foreground-muted hover:bg-white/[0.055] hover:text-foreground',
      )}
    >
      <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 text-foreground-subtle" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium leading-4">{conversation.title}</div>
        {searchResult?.matches.length ? (
          <div className="mt-1 space-y-0.5">
            {searchResult.matches.slice(0, 2).map((match) => (
              <div key={match.message_id} className="text-[11px] leading-tight text-foreground-subtle">
                <HighlightSnippet snippet={match.snippet} ranges={match.highlight_ranges} />
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-0.5 truncate text-[11px] text-foreground-subtle">
            {conversation.messageCount} 条消息 · {formatTime(conversation.updatedAt)}
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-0.5">
        <SidebarIconButton title="导出" onClick={(event) => { event.stopPropagation(); onExport(); }}>
          <Download className="h-3.5 w-3.5" />
        </SidebarIconButton>
        <SidebarIconButton title="删除" danger onClick={(event) => { event.stopPropagation(); onDelete(); }}>
          <Trash2 className="h-3.5 w-3.5" />
        </SidebarIconButton>
      </div>
    </div>
  );
}

function ExportModal({
  conversation,
  onClose,
}: {
  conversation: Conversation;
  onClose: () => void;
}) {
  const [options, setOptions] = useState<ExportConversationOptions>(() => defaultExportOptions(conversation.title));
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');

  const setOption = <K extends keyof ExportConversationOptions>(key: K, value: ExportConversationOptions[K]) => {
    setOptions((current) => ({ ...current, [key]: value }));
  };

  const checkbox = (key: keyof ExportConversationOptions, label: string, note?: string) => (
    <label className="flex items-start gap-2 rounded-lg px-2 py-1.5 text-[12px] text-foreground-muted transition-colors hover:bg-white/[0.045] hover:text-foreground">
      <input
        type="checkbox"
        checked={Boolean(options[key])}
        onChange={(event) => setOption(key as any, event.target.checked as any)}
        className="mt-0.5 rounded border-white/15 bg-[#151515]"
      />
      <span className="min-w-0">
        <span className="block text-foreground">{label}</span>
        {note && <span className="block text-[11px] text-foreground-subtle">{note}</span>}
      </span>
    </label>
  );

  const saveBlob = async () => {
    setError('');
    setExporting(true);
    try {
      const { blob, filename } = await exportConversation(conversation.id, options);
      if ('showSaveFilePicker' in window) {
        try {
          const handle = await (window as any).showSaveFilePicker({
            suggestedName: filename,
            types: [
              {
                description: 'Conversation export',
                accept: {
                  [options.format === 'html' ? 'text/html' : options.format === 'txt' ? 'text/plain' : 'text/markdown']:
                    [`.${options.format}`],
                },
              },
            ],
          });
          const writer = await handle.createWritable();
          await writer.write(blob);
          await writer.close();
          onClose();
          return;
        } catch (saveError: any) {
          if (saveError?.name === 'AbortError') return;
          throw saveError;
        }
      }
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
      onClose();
    } catch (exportError: any) {
      setError(exportError?.message || String(exportError));
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/55 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
        <div
          className="w-full max-w-2xl overflow-hidden rounded-2xl border border-white/10 bg-[#1d1d1d] shadow-[0_24px_80px_rgba(0,0,0,0.55)]"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="border-b border-white/10 bg-[radial-gradient(circle_at_20%_0%,rgba(99,102,241,0.22),transparent_34%),#202020] px-5 py-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="text-sm font-semibold text-foreground">导出会话模板</div>
                <div className="mt-1 truncate text-xs text-foreground-subtle">{conversation.title}</div>
              </div>
              <button className="rounded-lg p-1 text-foreground-muted hover:bg-white/10 hover:text-foreground" onClick={onClose}>
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div className="grid max-h-[70vh] gap-4 overflow-y-auto p-5 md:grid-cols-[220px_1fr]">
            <div className="space-y-3">
              <div>
                <div className="mb-1 text-[11px] font-medium text-foreground-subtle">格式</div>
                <div className="grid grid-cols-3 gap-1 rounded-xl bg-black/20 p-1">
                  {(['html', 'md', 'txt'] as const).map((format) => (
                    <button
                      key={format}
                      type="button"
                      onClick={() => setOption('format', format)}
                      className={cn(
                        'rounded-lg px-2 py-1.5 text-xs font-medium transition-colors',
                        options.format === format ? 'bg-white/12 text-foreground' : 'text-foreground-muted hover:text-foreground',
                      )}
                    >
                      {format.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-medium text-foreground-subtle">模板标题</label>
                <input
                  value={options.customTitle || ''}
                  onChange={(event) => setOption('customTitle', event.target.value)}
                  className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-foreground outline-none transition-colors focus:border-white/20"
                />
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-medium text-foreground-subtle">模型名称</label>
                <select
                  value={options.modelNameMode}
                  onChange={(event) => setOption('modelNameMode', event.target.value as ExportConversationOptions['modelNameMode'])}
                  className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-foreground outline-none"
                >
                  <option value="generic">通用名称</option>
                  <option value="actual">真实模型</option>
                  <option value="custom">自定义</option>
                  <option value="hidden">隐藏</option>
                </select>
              </div>
              {options.modelNameMode === 'custom' && (
                <input
                  value={options.customModelName || ''}
                  onChange={(event) => setOption('customModelName', event.target.value)}
                  placeholder="例如：研究助手"
                  className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-foreground outline-none"
                />
              )}
            </div>
            <div className="space-y-3">
              <div className="grid gap-1 sm:grid-cols-2">
                {checkbox('anonymize', '匿名化个人信息', '隐藏本地路径、UUID、邮箱、密钥样式文本')}
                {checkbox('includeBasicInfo', '基础信息')}
                {checkbox('includeWorkspace', 'Workspace 信息')}
                {checkbox('includeModelName', '模型名称')}
                {checkbox('includeUserMessages', '用户消息')}
                {checkbox('includeAssistantMessages', '助手消息')}
                {checkbox('includeFinalText', '最终回复文本')}
                {checkbox('includeThinking', 'Thinking 标签')}
                {checkbox('includeExecution', '处理回合')}
                {checkbox('includeToolCalls', 'Tool 标签')}
                {checkbox('includeToolPayload', 'Tool 参数', '默认关闭，避免外泄路径和敏感输入')}
                {checkbox('includeToolResult', 'Tool 结果')}
                {checkbox('includeToolErrors', 'Tool 错误')}
                {checkbox('includeAttachments', '附件列表')}
                {checkbox('includeSystemEvents', '系统/工作流事件')}
              </div>
              {error && <div className="rounded-xl border border-error/30 bg-error/10 px-3 py-2 text-xs text-error">{error}</div>}
            </div>
          </div>
          <div className="flex items-center justify-between gap-3 border-t border-white/10 px-5 py-3">
            <div className="text-[11px] text-foreground-subtle">默认使用 HTML 精美模板，适合外发；Markdown 适合归档。</div>
            <button
              type="button"
              onClick={saveBlob}
              disabled={exporting}
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:opacity-60"
            >
              <Download className="h-4 w-4" />
              {exporting ? '导出中' : '导出'}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function CreateProjectModal({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (input: { name: string; directoryPath?: string }) => Promise<void>;
}) {
  const [name, setName] = useState('');
  const [directoryPath, setDirectoryPath] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const chooseDirectory = async () => {
    setError('');
    try {
      if ('showDirectoryPicker' in window) {
        const handle = await (window as any).showDirectoryPicker({ mode: 'readwrite' });
        setDirectoryPath(handle.name || '');
        if (!name.trim()) setName(handle.name || '新项目');
        return;
      }
      setError('当前浏览器不暴露原生目录选择器，请手动输入本地目录路径。');
    } catch (err: any) {
      if (err?.name !== 'AbortError') setError(err?.message || String(err));
    }
  };

  const submit = async () => {
    const projectName = name.trim() || directoryPath.split(/[\\/]/).filter(Boolean).pop() || '新项目';
    setCreating(true);
    setError('');
    try {
      await onCreate({ name: projectName, directoryPath: directoryPath.trim() || undefined });
      onClose();
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/55 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
        <div
          className="w-full max-w-lg overflow-hidden rounded-2xl border border-white/10 bg-[#1d1d1d] shadow-[0_24px_80px_rgba(0,0,0,0.55)]"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="bg-[radial-gradient(circle_at_15%_-10%,rgba(34,211,238,0.22),transparent_34%),radial-gradient(circle_at_78%_0%,rgba(168,85,247,0.22),transparent_28%),#202020] px-5 py-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold text-foreground">创建项目 Workspace</div>
                <div className="mt-1 text-xs text-foreground-subtle">选择目录后会创建项目 workspace，并自动新建第一条会话。</div>
              </div>
              <button className="rounded-lg p-1 text-foreground-muted hover:bg-white/10 hover:text-foreground" onClick={onClose}>
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div className="space-y-4 p-5">
            <div>
              <label className="mb-1 block text-[11px] font-medium text-foreground-subtle">项目名称</label>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="例如 VonishAgent"
                className="w-full rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-foreground outline-none transition-colors focus:border-white/20"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-medium text-foreground-subtle">本地目录</label>
              <div className="flex gap-2">
                <input
                  value={directoryPath}
                  onChange={(event) => setDirectoryPath(event.target.value)}
                  placeholder="F:\\Projects\\YourProject"
                  className="min-w-0 flex-1 rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-foreground outline-none transition-colors focus:border-white/20"
                />
                <button
                  type="button"
                  onClick={chooseDirectory}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 px-3 py-2 text-sm text-foreground-muted transition-colors hover:bg-white/[0.07] hover:text-foreground"
                >
                  <Folder className="h-4 w-4" />
                  选择
                </button>
              </div>
              <div className="mt-1 text-[11px] text-foreground-subtle">
                浏览器无法读取完整路径时，可手动填入；后端会创建内部 workspace 并记录该目录。
              </div>
            </div>
            {error && <div className="rounded-xl border border-error/30 bg-error/10 px-3 py-2 text-xs text-error">{error}</div>}
          </div>
          <div className="flex items-center justify-end gap-2 border-t border-white/10 px-5 py-3">
            <button className="rounded-xl px-3 py-2 text-sm text-foreground-muted hover:bg-white/[0.06]" onClick={onClose}>
              取消
            </button>
            <button
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-60"
              onClick={submit}
              disabled={creating}
            >
              <FolderPlus className="h-4 w-4" />
              {creating ? '创建中' : '创建项目'}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

export function Sidebar({ className }: SidebarProps) {
  const {
    sidebarOpen,
    sidebarWidth,
    setSidebarWidth,
    toggleSidebar,
    sidebarHoverOpen,
    setSidebarHoverOpen,
    isMobile,
    mobileSidebarOpen,
    setMobileSidebarOpen,
  } = useUIStore();
  const {
    conversations,
    currentConversationId,
    selectConversation,
    deleteConversation,
    createConversation,
    createProject,
    renameProject,
    deleteProject,
    clearAll,
  } = useChatStore();
  const loadWorkspaceList = useWorkspaceStore((state) => state.loadWorkspaceList);
  const setDraftWorkspaceId = useSessionDraftStore((state) => state.setWorkspaceId);
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState<'chats' | 'files'>('chats');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<ConversationSearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [projectsExpanded, setProjectsExpanded] = useState(true);
  const [conversationsExpanded, setConversationsExpanded] = useState(true);
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(() => new Set());
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [exportConversationId, setExportConversationId] = useState<string | null>(null);
  const [renameProjectId, setRenameProjectId] = useState<string | null>(null);
  const [renameProjectText, setRenameProjectText] = useState('');
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  useEffect(() => {
    void loadWorkspaceList();
  }, [loadWorkspaceList]);

  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    const query = searchQuery.trim();
    if (!query) {
      setSearchResults([]);
      setSearchLoading(false);
      return;
    }
    setSearchLoading(true);
    searchTimerRef.current = setTimeout(async () => {
      try {
        const data = await searchConversations(query);
        setSearchResults(data.results);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 220);
    return () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    };
  }, [searchQuery]);

  const isSearching = searchQuery.trim().length > 0;
  const displayConversations: Conversation[] = isSearching
    ? searchResults.map((result) => ({
        id: result.conversation_id,
        title: result.title,
        messages: [],
        model: '',
        createdAt: new Date(result.updated_at).getTime(),
        updatedAt: new Date(result.updated_at).getTime(),
        messageCount: result.matches.length,
        metadata: {},
      }))
    : conversations;

  const projectGroups = useMemo(() => {
    return conversations
      .reduce<Array<{ id: string; name: string; workspaceId: string; conversations: Conversation[] }>>((items, conversation) => {
        const projectId = String(conversation.metadata?.project_id ?? '');
        if (!projectId) return items;
        let group = items.find((item) => item.id === projectId);
        if (!group) {
          group = {
            id: projectId,
            name: String(conversation.metadata?.project_name ?? projectId),
            workspaceId: String(conversation.metadata?.workspace_id ?? projectId),
            conversations: [],
          };
          items.push(group);
        }
        group.conversations.push(conversation);
        return items;
      }, [])
      .sort((a, b) => Math.max(...b.conversations.map((c) => c.updatedAt)) - Math.max(...a.conversations.map((c) => c.updatedAt)));
  }, [conversations]);

  const looseConversations = isSearching ? displayConversations : displayConversations.filter((conversation) => !conversation.metadata?.project_id);
  const exportTarget = exportConversationId ? conversations.find((conversation) => conversation.id === exportConversationId) : undefined;

  const handleMouseDown = useCallback(
    (event: React.MouseEvent) => {
      dragRef.current = { startX: event.clientX, startWidth: sidebarWidth };
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      const move = (moveEvent: MouseEvent) => {
        if (!dragRef.current) return;
        setSidebarWidth(dragRef.current.startWidth + moveEvent.clientX - dragRef.current.startX);
      };
      const up = () => {
        dragRef.current = null;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        document.removeEventListener('mousemove', move);
        document.removeEventListener('mouseup', up);
      };
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', up);
    },
    [setSidebarWidth, sidebarWidth],
  );

  const handleMouseEnter = useCallback(() => {
    if (!sidebarOpen && !isMobile) {
      if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
      setSidebarHoverOpen(true);
    }
  }, [isMobile, setSidebarHoverOpen, sidebarOpen]);

  const handleMouseLeave = useCallback(() => {
    if (!sidebarOpen && !isMobile) {
      hoverTimeoutRef.current = setTimeout(() => setSidebarHoverOpen(false), 260);
    }
  }, [isMobile, setSidebarHoverOpen, sidebarOpen]);

  useEffect(() => () => {
    if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
  }, []);

  const toggleProject = (projectId: string) => {
    setExpandedProjects((current) => {
      const next = new Set(current);
      if (next.has(projectId)) next.delete(projectId);
      else next.add(projectId);
      return next;
    });
  };

  const selectProjectConversation = (conversation: Conversation) => {
    setDraftWorkspaceId(String(conversation.metadata?.project_id || conversation.metadata?.workspace_id || ''));
    void selectConversation(conversation.id);
    setSearchQuery('');
  };

  const createProjectAndExpand = async (input: { name: string; directoryPath?: string }) => {
    const projectId = await createProject(input);
    setProjectsExpanded(true);
    setExpandedProjects((current) => new Set(current).add(projectId));
  };

  const sidebarBody = (
    <>
      <div className="flex items-center justify-between px-3 py-3">
        <div>
          <div className="text-[13px] font-semibold text-foreground">VonishAgent</div>
          <div className="text-[11px] text-foreground-subtle">Workspace Console</div>
        </div>
        <Tooltip content="收起">
          <button className="rounded-lg p-1.5 text-foreground-muted hover:bg-white/[0.06] hover:text-foreground" onClick={toggleSidebar}>
            <ChevronLeft className="h-4 w-4" />
          </button>
        </Tooltip>
      </div>

      <div className="px-2">
        <div className="grid grid-cols-2 gap-1 rounded-xl bg-black/20 p-1">
          <button
            onClick={() => setActiveTab('chats')}
            className={cn('rounded-lg px-2 py-1.5 text-xs font-medium transition-colors', activeTab === 'chats' ? 'bg-white/10 text-foreground' : 'text-foreground-muted hover:text-foreground')}
          >
            对话
          </button>
          <button
            onClick={() => setActiveTab('files')}
            className={cn('rounded-lg px-2 py-1.5 text-xs font-medium transition-colors', activeTab === 'files' ? 'bg-white/10 text-foreground' : 'text-foreground-muted hover:text-foreground')}
          >
            文件
          </button>
        </div>
      </div>

      {activeTab === 'chats' ? (
        <>
          <div className="space-y-2 px-2 py-3">
            <button
              onClick={() => {
                setDraftWorkspaceId(null);
                void createConversation();
              }}
              className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.055] px-3 py-2 text-[13px] font-medium text-foreground transition-colors hover:bg-white/[0.085]"
            >
              <Plus className="h-4 w-4" />
              新对话
            </button>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-foreground-subtle" />
              <input
                type="text"
                placeholder={searchLoading ? '搜索中...' : t('chat.search')}
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                className="w-full rounded-xl border border-white/10 bg-black/20 py-2 pl-9 pr-3 text-[13px] text-foreground outline-none transition-colors placeholder:text-foreground-subtle focus:border-white/20 focus:bg-black/25"
              />
            </div>
          </div>

          {!isSearching && (
            <div className="px-2">
              <SectionHeader
                icon={<Folder className="h-3.5 w-3.5" />}
                title="项目"
                count={projectGroups.length}
                expanded={projectsExpanded}
                onToggle={() => setProjectsExpanded((value) => !value)}
                action={
                  <button
                    type="button"
                    title="新建项目"
                    onClick={() => setCreateProjectOpen(true)}
                    className="grid h-7 w-7 place-items-center rounded-lg text-foreground-subtle transition-colors hover:bg-white/[0.07] hover:text-foreground"
                  >
                    <FolderPlus className="h-4 w-4" />
                  </button>
                }
              />
              {projectsExpanded && (
                <div className="space-y-1">
                  {projectGroups.map((project) => {
                    const expanded = expandedProjects.has(project.id);
                    return (
                      <div key={project.id}>
                        <div className="group flex min-h-9 items-center gap-1 rounded-xl px-2 py-1 text-[13px] text-foreground-muted transition-colors hover:bg-white/[0.055] hover:text-foreground">
                          <button className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={() => toggleProject(project.id)}>
                            <span className="grid h-4 w-4 place-items-center text-foreground-subtle">
                              {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                            </span>
                            <Folder className="h-3.5 w-3.5 shrink-0 text-foreground-subtle" />
                            {renameProjectId === project.id ? (
                              <input
                                value={renameProjectText}
                                onChange={(event) => setRenameProjectText(event.target.value)}
                                onClick={(event) => event.stopPropagation()}
                                onKeyDown={(event) => {
                                  if (event.key === 'Enter') {
                                    void renameProject(project.id, renameProjectText.trim() || project.name);
                                    setRenameProjectId(null);
                                  }
                                  if (event.key === 'Escape') setRenameProjectId(null);
                                }}
                                onBlur={() => {
                                  void renameProject(project.id, renameProjectText.trim() || project.name);
                                  setRenameProjectId(null);
                                }}
                                className="min-w-0 flex-1 rounded-md border border-white/15 bg-black/30 px-1.5 py-0.5 text-xs text-foreground outline-none"
                                autoFocus
                              />
                            ) : (
                              <span className="min-w-0 flex-1 truncate">{project.name}</span>
                            )}
                            <span className="text-[11px] text-foreground-subtle">{project.conversations.length}</span>
                          </button>
                          <SidebarIconButton
                            title="新建项目会话"
                            onClick={(event) => {
                              event.stopPropagation();
                              setDraftWorkspaceId(project.id);
                              void createConversation();
                              setExpandedProjects((current) => new Set(current).add(project.id));
                            }}
                          >
                            <Plus className="h-3.5 w-3.5" />
                          </SidebarIconButton>
                          <SidebarIconButton
                            title="重命名项目"
                            onClick={(event) => {
                              event.stopPropagation();
                              setRenameProjectId(project.id);
                              setRenameProjectText(project.name);
                            }}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </SidebarIconButton>
                          <SidebarIconButton
                            title="删除项目"
                            danger
                            onClick={(event) => {
                              event.stopPropagation();
                              if (window.confirm(`删除项目“${project.name}”及其所有会话和文件？`)) void deleteProject(project.id);
                            }}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </SidebarIconButton>
                        </div>
                        {expanded && (
                          <div className="mt-1 space-y-1">
                            {project.conversations.map((conversation) => (
                              <ConversationRow
                                key={conversation.id}
                                conversation={conversation}
                                active={currentConversationId === conversation.id}
                                nested
                                onSelect={() => selectProjectConversation(conversation)}
                                onExport={() => setExportConversationId(conversation.id)}
                                onDelete={() => {
                                  if (window.confirm('删除该会话？')) void deleteConversation(conversation.id);
                                }}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
            <SectionHeader
              icon={<MessageSquare className="h-3.5 w-3.5" />}
              title={isSearching ? '搜索结果' : '对话'}
              count={looseConversations.length}
              expanded={conversationsExpanded}
              onToggle={() => setConversationsExpanded((value) => !value)}
            />
            {conversationsExpanded && (
              <div className="space-y-1">
                {looseConversations.map((conversation) => (
                  <ConversationRow
                    key={conversation.id}
                    conversation={conversation}
                    active={currentConversationId === conversation.id}
                    searchResult={isSearching ? searchResults.find((result) => result.conversation_id === conversation.id) : undefined}
                    onSelect={() => {
                      void selectConversation(conversation.id);
                      setDraftWorkspaceId(null);
                      setSearchQuery('');
                    }}
                    onExport={() => setExportConversationId(conversation.id)}
                    onDelete={() => {
                      if (window.confirm('删除该会话？')) void deleteConversation(conversation.id);
                    }}
                  />
                ))}
              </div>
            )}
          </div>

          {!isSearching && conversations.length > 0 && (
            <div className="border-t border-white/8 p-2">
              <button
                className="flex w-full items-center gap-2 rounded-xl px-2 py-2 text-left text-xs text-error/80 transition-colors hover:bg-error/10 hover:text-error"
                onClick={() => {
                  if (window.confirm('清空所有项目、会话和工作目录？此操作不可撤销。')) void clearAll();
                }}
              >
                <Trash2 className="h-3.5 w-3.5" />
                清空所有项目和对话
              </button>
            </div>
          )}
        </>
      ) : (
        <WorkspacePanel currentConversationId={currentConversationId} />
      )}
    </>
  );

  if (isMobile) {
    return (
      <>
        {mobileSidebarOpen && (
          <>
            <div className="fixed inset-0 z-40 bg-black/55" onClick={() => setMobileSidebarOpen(false)} />
            <aside className={cn('fixed bottom-0 left-0 top-0 z-50 flex w-[300px] flex-col border-r border-white/10 bg-[#111111]', className)}>
              {sidebarBody}
            </aside>
            {createProjectOpen && <CreateProjectModal onClose={() => setCreateProjectOpen(false)} onCreate={createProjectAndExpand} />}
            {exportTarget && <ExportModal conversation={exportTarget} onClose={() => setExportConversationId(null)} />}
          </>
        )}
      </>
    );
  }

  if (!sidebarOpen) {
    return (
      <div className="relative flex-shrink-0" onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}>
        <div className={cn('flex h-full w-10 flex-col items-center gap-2 border-r border-white/8 bg-[#0f0f0f] py-3', className)}>
          <button className="rounded-lg p-1.5 text-foreground-muted hover:bg-white/[0.07] hover:text-foreground" onClick={toggleSidebar}>
            <ChevronRight className="h-4 w-4" />
          </button>
          <div className="h-px w-5 bg-white/10" />
          <button className="rounded-lg p-1.5 text-foreground-muted hover:bg-white/[0.07] hover:text-foreground" onClick={() => void createConversation()}>
            <MessageSquare className="h-4 w-4" />
          </button>
        </div>
        {sidebarHoverOpen && (
          <div className="absolute left-full top-2 z-40 ml-2 w-[240px] overflow-hidden rounded-2xl border border-white/10 bg-[#1d1d1d] shadow-2xl">
            <div className="border-b border-white/8 px-3 py-2 text-xs font-medium text-foreground">最近对话</div>
            <div className="max-h-[360px] space-y-1 overflow-y-auto p-2">
              {conversations.slice(0, 8).map((conversation) => (
                <button
                  key={conversation.id}
                  className="flex w-full items-center gap-2 rounded-xl px-2 py-2 text-left text-xs text-foreground-muted hover:bg-white/[0.06] hover:text-foreground"
                  onClick={() => {
                    void selectConversation(conversation.id);
                    setSidebarHoverOpen(false);
                    toggleSidebar();
                  }}
                >
                  <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{conversation.title}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <aside
      className={cn('relative flex flex-shrink-0 flex-col border-r border-white/8 bg-[#101010]', className)}
      style={{ width: sidebarWidth }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div className="absolute bottom-0 right-0 top-0 z-30 w-1.5 cursor-col-resize transition-colors hover:bg-primary/35" onMouseDown={handleMouseDown} />
      {sidebarBody}
      {createProjectOpen && <CreateProjectModal onClose={() => setCreateProjectOpen(false)} onCreate={createProjectAndExpand} />}
      {exportTarget && <ExportModal conversation={exportTarget} onClose={() => setExportConversationId(null)} />}
    </aside>
  );
}
