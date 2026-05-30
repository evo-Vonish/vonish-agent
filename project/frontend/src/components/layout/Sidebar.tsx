import { useState, useRef, useCallback, useEffect } from 'react';
import {
  Search,
  MessageSquare,
  ChevronDown,
  ChevronRight,
  FolderOpen,
  FileText,
  Folder,
  Trash2,
  Download,
  ChevronLeft,
  ChevronRight as ChevronRightIcon,
  X,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useI18n } from '@/i18n';
import type { FileNode } from '@/types';
import { formatTime } from '@/lib/utils';
import { Tooltip } from '@/components/ui/Tooltip';
import { searchConversations, type ConversationSearchResult } from '@/services/api';

interface SidebarProps {
  className?: string;
}

function HighlightSnippet({ snippet, ranges }: { snippet: string; ranges: [number, number][] }) {
  if (!ranges.length) return <>{snippet}</>;
  const parts: React.ReactNode[] = [];
  let last = 0;
  ranges.forEach(([start, end], i) => {
    if (start > last) {
      parts.push(<span key={`t-${i}`}>{snippet.slice(last, start)}</span>);
    }
    parts.push(
      <mark key={`m-${i}`} className="bg-primary/20 text-primary rounded px-0.5">
        {snippet.slice(start, end)}
      </mark>
    );
    last = end;
  });
  if (last < snippet.length) {
    parts.push(<span key="tail">{snippet.slice(last)}</span>);
  }
  return <>{parts}</>;
}

function FileTreeItem({ node, depth = 0 }: { node: FileNode; depth?: number }) {
  const [expanded, setExpanded] = useState(true);
  const isFolder = node.type === 'folder';

  return (
    <div>
      <button
        onClick={() => isFolder && setExpanded(!expanded)}
        className={cn(
          'w-full flex items-center gap-1.5 px-2 py-[3px] text-xs rounded-md',
          'hover:bg-surface-hover transition-colors text-left',
          'text-foreground-muted hover:text-foreground'
        )}
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
      >
        {isFolder ? (
          <span className="flex-shrink-0">
            {expanded ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronRight className="w-3 h-3" />
            )}
          </span>
        ) : (
          <span className="w-3 flex-shrink-0" />
        )}
        {isFolder ? (
          <Folder className="w-3.5 h-3.5 text-primary flex-shrink-0" />
        ) : (
          <FileText className="w-3.5 h-3.5 text-foreground-subtle flex-shrink-0" />
        )}
        <span className="truncate">{node.name}</span>
      </button>
      {isFolder && expanded && node.children && (
        <div>
          {node.children.map((child) => (
            <FileTreeItem key={child.id} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
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
  const { conversations, currentConversationId, selectConversation, deleteConversation, createConversation } =
    useChatStore();
  const { fileTree, loading: wsLoading, loaded: wsLoaded } = useWorkspaceStore();
  const { t } = useI18n();
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<'chats' | 'files'>('chats');
  const [deleteMenuOpen, setDeleteMenuOpen] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState('md');
  const [anonymize, setAnonymize] = useState(false);
  const [renameOpen, setRenameOpen] = useState<string | null>(null);
  const [renameText, setRenameText] = useState('');
  const [searchResults, setSearchResults] = useState<ConversationSearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const handleExport = async () => {
    if (!exportOpen) return;
    setExporting(true);
    try {
      const params = new URLSearchParams({
        format: exportFormat,
        anonymize: String(anonymize),
        customTitle: conversations.find(c => c.id === exportOpen)?.title || 'conversation',
      });
      const response = await fetch(`/api/conversations/${exportOpen}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          format: exportFormat,
          anonymize,
          customTitle: conversations.find(c => c.id === exportOpen)?.title || 'conversation',
        }),
      });
      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const disposition = response.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename="(.+)"/);
        a.download = match?.[1] || `export.${exportFormat}`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch {} finally {
      setExporting(false);
      setExportOpen(null);
    }
  };

  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const renameRef = useRef<HTMLInputElement>(null);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (renameOpen && renameRef.current) renameRef.current.focus();
  }, [renameOpen]);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      dragRef.current = { startX: e.clientX, startWidth: sidebarWidth };
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';

      const handleMouseMove = (e: MouseEvent) => {
        if (!dragRef.current) return;
        const delta = e.clientX - dragRef.current.startX;
        setSidebarWidth(dragRef.current.startWidth + delta);
      };

      const handleMouseUp = () => {
        dragRef.current = null;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    },
    [sidebarWidth, setSidebarWidth]
  );

  const handleMouseEnter = useCallback(() => {
    if (!sidebarOpen && !isMobile) {
      if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
      setSidebarHoverOpen(true);
    }
  }, [sidebarOpen, isMobile, setSidebarHoverOpen]);

  const handleMouseLeave = useCallback(() => {
    if (!sidebarOpen && !isMobile) {
      hoverTimeoutRef.current = setTimeout(() => {
        setSidebarHoverOpen(false);
      }, 300);
    }
  }, [sidebarOpen, isMobile, setSidebarHoverOpen]);

  useEffect(() => {
    return () => {
      if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    };
  }, []);

  // Debounced backend search
  useEffect(() => {
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    const q = searchQuery.trim();
    if (!q) {
      setSearchResults([]);
      setSearchLoading(false);
      return;
    }
    setSearchLoading(true);
    searchTimerRef.current = setTimeout(async () => {
      try {
        const data = await searchConversations(q);
        setSearchResults(data.results);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 300);
    return () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    };
  }, [searchQuery]);

  const isSearching = searchQuery.trim().length > 0;
  const displayConversations = isSearching
    ? searchResults.map((r) => ({
        id: r.conversation_id,
        title: r.title,
        updatedAt: new Date(r.updated_at).getTime(),
        messageCount: r.matches.length,
      }))
    : conversations;

  // Mobile drawer overlay
  if (isMobile) {
    return (
      <>
        {mobileSidebarOpen && (
          <>
            <div
              className="fixed inset-0 bg-black/50 z-40"
              onClick={() => setMobileSidebarOpen(false)}
            />
            <aside
              className={cn(
                'fixed left-0 top-0 bottom-0 w-[280px] bg-surface border-r border-border z-50 flex flex-col',
                className
              )}
            >
              {/* Mobile sidebar header */}
              <div className="flex items-center justify-between px-3 py-2 border-b border-border">
                <span className="text-xs font-semibold text-foreground">工作台</span>
                <button
                  onClick={() => setMobileSidebarOpen(false)}
                  className="p-1 rounded hover:bg-surface-hover text-foreground-muted"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              {/* Search */}
              <div className="px-2 py-2">
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground-subtle" />
                  <input
                    type="text"
                    placeholder={t('chat.search')}
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-7 pr-2 py-1.5 text-xs rounded-lg bg-background border border-border text-foreground placeholder:text-foreground-subtle focus:outline-none focus:border-primary/50 transition-colors"
                  />
                </div>
              </div>
              {/* Conversation list */}
              <div className="flex-1 overflow-y-auto px-1 pb-2 space-y-0.5">
                {displayConversations.map((conv) => {
                  const searchResult = isSearching
                    ? searchResults.find((r) => r.conversation_id === conv.id)
                    : undefined;
                  return (
                    <button
                      key={conv.id}
                      className={cn(
                        'w-full flex items-start gap-2 px-2.5 py-2 rounded-md text-left transition-colors',
                        currentConversationId === conv.id
                          ? 'bg-primary/10 text-foreground'
                          : 'text-foreground-muted hover:bg-surface-hover hover:text-foreground'
                      )}
                      onClick={() => {
                        selectConversation(conv.id);
                        setMobileSidebarOpen(false);
                        setSearchQuery('');
                      }}
                    >
                      <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium truncate">{conv.title}</div>
                        {searchResult && searchResult.matches.length > 0 ? (
                          <div className="space-y-0.5 mt-0.5">
                            {searchResult.matches.slice(0, 2).map((m) => (
                              <div key={m.message_id} className="text-[10px] text-foreground-subtle leading-tight">
                                <span className="opacity-50">
                                  {m.role === 'user' ? '我' : m.role === 'assistant' ? 'AI' : m.role}:
                                </span>{' '}
                                <HighlightSnippet snippet={m.snippet} ranges={m.highlight_ranges} />
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-[10px] opacity-50 truncate">
                            {conv.messageCount} {t('chat.messages')} · {formatTime(conv.updatedAt)}
                          </div>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            </aside>
          </>
        )}
      </>
    );
  }

  // Desktop collapsed sidebar
  if (!sidebarOpen) {
    return (
      <div
        className="relative flex-shrink-0"
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        {/* Collapsed bar */}
        <div
          className={cn(
            'w-9 border-r border-border bg-surface flex flex-col items-center py-3 gap-2 h-full',
            className
          )}
        >
          <Tooltip content="展开侧边栏">
            <button
              onClick={toggleSidebar}
              className="p-1.5 rounded-md hover:bg-surface-hover text-foreground-muted hover:text-foreground transition-colors"
            >
              <ChevronRightIcon className="w-4 h-4" />
            </button>
          </Tooltip>
          <div className="w-5 h-px bg-border" />
          <Tooltip content="新对话">
            <button
              onClick={() => createConversation()}
              className="p-1.5 rounded-md hover:bg-surface-hover text-foreground-muted hover:text-foreground transition-colors"
            >
              <MessageSquare className="w-4 h-4" />
            </button>
          </Tooltip>
        </div>

        {/* Hover expand panel */}
        {sidebarHoverOpen && (
          <div
            className={cn(
              'absolute left-full top-0 ml-1 w-[240px] bg-surface-elevated border border-border rounded-xl shadow-2xl z-40',
              'flex flex-col max-h-[80vh] overflow-hidden'
            )}
          >
            <div className="p-2 border-b border-border">
              <span className="text-xs font-medium text-foreground">{t('chat.title')}</span>
            </div>
            <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
              {conversations.slice(0, 5).map((conv) => (
                <button
                  key={conv.id}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left text-xs text-foreground-muted hover:bg-surface-hover hover:text-foreground transition-colors"
                  onClick={() => {
                    selectConversation(conv.id);
                    setSidebarHoverOpen(false);
                    toggleSidebar();
                  }}
                >
                  <MessageSquare className="w-3 h-3 flex-shrink-0" />
                  <span className="truncate">{conv.title}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  // Desktop expanded sidebar
  return (
    <aside
      className={cn(
        'flex-shrink-0 border-r border-border bg-surface flex flex-col relative',
        className
      )}
      style={{ width: sidebarWidth }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Resize handle */}
      <div
        className="absolute right-0 top-0 bottom-0 w-1.5 cursor-col-resize z-30 hover:bg-primary/40 transition-colors"
        onMouseDown={handleMouseDown}
      />

      {/* Header with collapse */}
      <div className="flex items-center justify-between px-3 py-2">
        <span className="text-xs font-medium text-foreground-subtle">工作台</span>
        <Tooltip content="收起">
          <button
            onClick={toggleSidebar}
            className="p-1 rounded hover:bg-surface-hover text-foreground-muted hover:text-foreground transition-colors"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>
        </Tooltip>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border px-2">
        <button
          onClick={() => setActiveTab('chats')}
          className={cn(
            'flex-1 px-2 py-2 text-xs font-medium transition-colors border-b-2 flex items-center justify-center gap-1.5',
            activeTab === 'chats'
              ? 'text-foreground border-primary'
              : 'text-foreground-muted border-transparent hover:text-foreground'
          )}
        >
          <MessageSquare className="w-3.5 h-3.5" />
          {t('nav.conversations')}
        </button>
        <button
          onClick={() => setActiveTab('files')}
          className={cn(
            'flex-1 px-2 py-2 text-xs font-medium transition-colors border-b-2 flex items-center justify-center gap-1.5',
            activeTab === 'files'
              ? 'text-foreground border-primary'
              : 'text-foreground-muted border-transparent hover:text-foreground'
          )}
        >
          <FolderOpen className="w-3.5 h-3.5" />
          {t('nav.files')}
        </button>
      </div>

      {/* New chat button + search */}
      {activeTab === 'chats' && (
        <>
          <div className="p-2">
            <button
              onClick={() => createConversation()}
              className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 transition-colors mb-2"
            >
              <MessageSquare className="w-3.5 h-3.5" />
              {t('chat.new')}
            </button>
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground-subtle" />
              <input
                type="text"
                placeholder={t('chat.search')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-7 pr-2 py-1.5 text-xs rounded-lg bg-background border border-border text-foreground placeholder:text-foreground-subtle focus:outline-none focus:border-primary/50 transition-colors"
              />
            </div>
          </div>

          {/* Conversation list */}
          <div className="flex-1 overflow-y-auto px-1.5 pb-2 space-y-0.5">
            {displayConversations.map((conv) => {
              const searchResult = isSearching
                ? searchResults.find((r) => r.conversation_id === conv.id)
                : undefined;
              return (
                <div
                  key={conv.id}
                  className={cn(
                    'group flex items-start gap-2 px-2.5 py-2 rounded-lg cursor-pointer transition-colors relative',
                    currentConversationId === conv.id
                      ? 'bg-primary/10 text-foreground'
                      : 'text-foreground-muted hover:bg-surface-hover hover:text-foreground'
                  )}
                  onClick={() => {
                    selectConversation(conv.id);
                    setSearchQuery('');
                  }}
                  onDoubleClick={() => {
                    if (!isSearching) {
                      setRenameOpen(conv.id);
                      setRenameText(conv.title);
                    }
                  }}
                >
                  <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    {renameOpen === conv.id && !isSearching ? (
                      <input
                        ref={renameRef}
                        value={renameText}
                        onChange={(e) => setRenameText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            conv.title = renameText;
                            setRenameOpen(null);
                          }
                          if (e.key === 'Escape') setRenameOpen(null);
                        }}
                        onBlur={() => {
                          conv.title = renameText;
                          setRenameOpen(null);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className="w-full text-xs bg-background border border-primary/50 rounded px-1 py-0.5 text-foreground outline-none"
                      />
                    ) : (
                      <>
                        <div className="text-xs font-medium truncate">{conv.title}</div>
                        {searchResult && searchResult.matches.length > 0 ? (
                          <div className="space-y-0.5 mt-0.5">
                            {searchResult.matches.slice(0, 2).map((m) => (
                              <div key={m.message_id} className="text-[10px] text-foreground-subtle leading-tight">
                                <span className="opacity-50">
                                  {m.role === 'user' ? '我' : m.role === 'assistant' ? 'AI' : m.role}:
                                </span>{' '}
                                <HighlightSnippet snippet={m.snippet} ranges={m.highlight_ranges} />
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-[10px] opacity-50 truncate">
                            {conv.messageCount} {t('chat.messages')} · {formatTime(conv.updatedAt)}
                          </div>
                        )}
                      </>
                    )}
                  </div>

                {/* Export button */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setExportOpen(conv.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-primary/20 hover:text-primary transition-all"
                  title={t('chat.export')}
                >
                  <Download className="w-3 h-3" />
                </button>

                {/* Delete button */}
                <div className="relative">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteMenuOpen(deleteMenuOpen === conv.id ? null : conv.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-error/20 hover:text-error transition-all"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>

                    {/* Confirmation popover */}
                    {deleteMenuOpen === conv.id && (
                      <>
                        <div className="fixed inset-0 z-40" onClick={(e) => { e.stopPropagation(); setDeleteMenuOpen(null); }} />
                        <div
                          className="absolute right-0 top-full mt-1 w-48 bg-surface-elevated border border-border rounded-xl shadow-2xl py-2 z-50 animate-in fade-in slide-in-from-top-1 duration-150"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <p className="px-3 pb-2 text-[11px] text-foreground-muted border-b border-border">
                            {t('chat.deleteConfirm')}
                          </p>
                          <button
                            onClick={() => {
                              deleteConversation(conv.id);
                              setDeleteMenuOpen(null);
                            }}
                            className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-error hover:bg-error/10 transition-colors"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            {t('chat.delete')}
                          </button>
                          <button
                            onClick={() => setDeleteMenuOpen(null)}
                            className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-foreground-muted hover:bg-surface-hover transition-colors"
                          >
                            {t('chat.cancel')}
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Export modal */}
      {exportOpen && (
        <>
          <div className="fixed inset-0 bg-black/50 z-50" onClick={() => setExportOpen(null)} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setExportOpen(null)}>
            <div className="bg-surface-elevated border border-border rounded-xl shadow-2xl w-full max-w-sm p-4 space-y-3 animate-in fade-in zoom-in-95 duration-150" onClick={(e) => e.stopPropagation()}>
              <h3 className="text-sm font-semibold text-foreground">{t('chat.export')}</h3>

              <div className="space-y-2">
                {/* Format */}
                <div>
                  <p className="text-[10px] text-foreground-muted mb-1">{t('chat.exportFormat')}</p>
                  <div className="flex gap-1.5">
                    {['md', 'txt'].map((f) => (
                      <button
                        key={f}
                        onClick={() => setExportFormat(f)}
                        className={cn(
                          'px-3 py-1 rounded-md text-xs border transition-colors',
                          exportFormat === f
                            ? 'border-primary/50 bg-primary/10 text-primary'
                            : 'border-border text-foreground-muted hover:bg-surface-hover'
                        )}
                      >
                        {f === 'md' ? 'Markdown' : 'TXT'}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Anonymize */}
                <label className="flex items-center gap-2 text-xs text-foreground-muted cursor-pointer">
                  <input
                    type="checkbox"
                    checked={anonymize}
                    onChange={(e) => setAnonymize(e.target.checked)}
                    className="rounded border-border"
                  />
                  {t('chat.anonymize')}
                </label>

                {/* Export button */}
                <button
                  onClick={handleExport}
                  disabled={exporting}
                  className="w-full py-2 rounded-lg bg-primary text-white text-xs font-medium hover:bg-primary-hover disabled:opacity-50 transition-colors"
                >
                  {exporting ? t('chat.exporting') : t('chat.exportDo')}
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* File tree */}
      {activeTab === 'files' && (
        <div className="flex-1 overflow-y-auto p-2">
          {!currentConversationId ? (
            <p className="text-xs text-foreground-subtle p-2">{t('nav.workspace.empty')}</p>
          ) : wsLoading ? (
            <div className="flex items-center gap-2 p-2 text-xs text-foreground-muted">
              <Loader2 className="w-3 h-3 animate-spin" />
              {t('nav.workspace.loading')}
            </div>
          ) : wsLoaded && fileTree.length === 0 ? (
            <p className="text-xs text-foreground-subtle p-2">{t('nav.workspace.noFiles')}</p>
          ) : (
            fileTree.map((node) => (
              <FileTreeItem key={node.id} node={node} />
            ))
          )}
        </div>
      )}
    </aside>
  );
}
