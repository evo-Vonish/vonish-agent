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
  ChevronLeft,
  ChevronRight as ChevronRightIcon,
  X,
  Wrench,
  Loader2,
} from 'lucide-react';
import { useHashRouter } from '@/hooks/useHashRouter';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import type { FileNode } from '@/types';
import { formatTime } from '@/lib/utils';
import { Tooltip } from '@/components/ui/Tooltip';

interface SidebarProps {
  className?: string;
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
  const { currentPath, navigate } = useHashRouter();
  const isToolsPage = currentPath === '/tools';
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<'chats' | 'files'>('chats');
  const [deleteMenuOpen, setDeleteMenuOpen] = useState<string | null>(null);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  const filteredConversations = conversations.filter((c) =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

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
              {/* Navigation buttons */}
              <div className="p-2 space-y-1.5">
                <button
                  onClick={() => {
                    navigate('/');
                    setMobileSidebarOpen(false);
                  }}
                  className={cn(
                    'w-full flex items-center gap-2 px-3 py-2 rounded-md text-xs font-medium transition-colors',
                    !isToolsPage
                      ? 'bg-primary/10 text-primary'
                      : 'text-foreground-muted hover:bg-surface-hover hover:text-foreground'
                  )}
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  对话
                </button>
                <button
                  onClick={() => {
                    navigate('/tools');
                    setMobileSidebarOpen(false);
                  }}
                  className={cn(
                    'w-full flex items-center gap-2 px-3 py-2 rounded-md text-xs font-medium transition-colors',
                    isToolsPage
                      ? 'bg-primary/10 text-primary'
                      : 'text-foreground-muted hover:bg-surface-hover hover:text-foreground'
                  )}
                >
                  <Wrench className="w-3.5 h-3.5" />
                  工具管理
                </button>
              </div>
              <div className="border-b border-border mx-2" />
              {/* Search */}
              <div className="px-2 pb-2">
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground-subtle" />
                  <input
                    type="text"
                    placeholder="搜索会话..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-7 pr-2 py-1.5 text-xs rounded-lg bg-background border border-border text-foreground placeholder:text-foreground-subtle focus:outline-none focus:border-primary/50 transition-colors"
                  />
                </div>
              </div>
              {/* Conversation list */}
              <div className="flex-1 overflow-y-auto px-1 pb-2 space-y-0.5">
                {filteredConversations.map((conv) => (
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
                    }}
                  >
                    <MessageSquare className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium truncate">{conv.title}</div>
                      <div className="text-[10px] opacity-50 truncate">{conv.messageCount} 条消息 · {formatTime(conv.updatedAt)}</div>
                    </div>
                  </button>
                ))}
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
              onClick={() => {
                navigate('/');
                createConversation();
              }}
              className="p-1.5 rounded-md hover:bg-surface-hover text-foreground-muted hover:text-foreground transition-colors"
            >
              <MessageSquare className="w-4 h-4" />
            </button>
          </Tooltip>
          <Tooltip content="工具管理">
            <button
              onClick={() => navigate('/tools')}
              className={cn(
                'p-1.5 rounded-md transition-colors',
                isToolsPage
                  ? 'bg-primary/10 text-primary'
                  : 'text-foreground-muted hover:bg-surface-hover hover:text-foreground'
              )}
            >
              <Wrench className="w-4 h-4" />
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
              <span className="text-xs font-medium text-foreground">最近会话</span>
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

      {/* Navigation */}
      <div className="flex gap-1 px-2 pb-2">
        <button
          onClick={() => navigate('/')}
          className={cn(
            'flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 text-xs font-medium rounded-md transition-colors',
            !isToolsPage
              ? 'bg-primary/10 text-primary'
              : 'text-foreground-muted hover:bg-surface-hover hover:text-foreground'
          )}
        >
          <MessageSquare className="w-3.5 h-3.5" />
          对话
        </button>
        <button
          onClick={() => navigate('/tools')}
          className={cn(
            'flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 text-xs font-medium rounded-md transition-colors',
            isToolsPage
              ? 'bg-primary/10 text-primary'
              : 'text-foreground-muted hover:bg-surface-hover hover:text-foreground'
          )}
        >
          <Wrench className="w-3.5 h-3.5" />
          工具
        </button>
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
          会话
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
          文件
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
              新对话
            </button>
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground-subtle" />
              <input
                type="text"
                placeholder="搜索会话..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-7 pr-2 py-1.5 text-xs rounded-lg bg-background border border-border text-foreground placeholder:text-foreground-subtle focus:outline-none focus:border-primary/50 transition-colors"
              />
            </div>
          </div>

          {/* Conversation list */}
          <div className="flex-1 overflow-y-auto px-1.5 pb-2 space-y-0.5">
            {filteredConversations.map((conv) => (
              <div
                key={conv.id}
                className={cn(
                  'group flex items-center gap-2 px-2.5 py-2 rounded-lg cursor-pointer transition-colors relative',
                  currentConversationId === conv.id
                    ? 'bg-primary/10 text-foreground'
                    : 'text-foreground-muted hover:bg-surface-hover hover:text-foreground'
                )}
                onClick={() => selectConversation(conv.id)}
              >
                <MessageSquare className="w-3.5 h-3.5 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium truncate">{conv.title}</div>
                  <div className="text-[10px] opacity-50 truncate">
                    {conv.messageCount} 条消息 · {formatTime(conv.updatedAt)}
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeleteMenuOpen(deleteMenuOpen === conv.id ? null : conv.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-error/20 hover:text-error transition-all"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {/* File tree */}
      {activeTab === 'files' && (
        <div className="flex-1 overflow-y-auto p-2">
          {!currentConversationId ? (
            <p className="text-xs text-foreground-subtle p-2">Select a conversation to view workspace files.</p>
          ) : wsLoading ? (
            <div className="flex items-center gap-2 p-2 text-xs text-foreground-muted">
              <Loader2 className="w-3 h-3 animate-spin" />
              Loading files...
            </div>
          ) : wsLoaded && fileTree.length === 0 ? (
            <p className="text-xs text-foreground-subtle p-2">No files in workspace yet.</p>
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
