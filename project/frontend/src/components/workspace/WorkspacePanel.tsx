import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Clock,
  Copy,
  ExternalLink,
  FilePlus2,
  FileText,
  Folder,
  FolderPlus,
  GitBranch,
  GitCompare,
  History,
  Image,
  Loader2,
  RefreshCw,
  Upload,
} from 'lucide-react';
import { cn, formatBytes } from '@/lib/utils';
import type { FileNode, GitDiffResult, GitHistoryResult, WorkspaceFilePreview } from '@/types';
import {
  createWorkspaceItem,
  getWorkspaceGitDiff,
  getWorkspaceGitHistory,
  previewWorkspaceFile,
  uploadWorkspaceFiles,
} from '@/services/api';
import { useChatStore } from '@/stores/chatStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useWorkbenchStore } from '@/stores/workbenchStore';
import { useI18n } from '@/i18n';

type PanelMode = 'preview' | 'diff' | 'history';

const gitBadge: Record<string, string> = {
  modified: 'M',
  added: 'A',
  deleted: 'D',
  untracked: 'U',
  conflict: '!',
};

function gitBadgeClass(status?: FileNode['gitStatus']) {
  if (status === 'modified') return 'bg-warning/15 text-warning';
  if (status === 'added') return 'bg-success/15 text-success';
  if (status === 'deleted') return 'bg-error/15 text-error';
  if (status === 'untracked') return 'bg-primary/15 text-primary';
  if (status === 'conflict') return 'bg-error/20 text-error';
  return '';
}

function FileTreeNode({
  node,
  depth = 0,
  selectedPath,
  onSelect,
  onInsert,
  onDiff,
  onHistory,
}: {
  node: FileNode;
  depth?: number;
  selectedPath?: string;
  onSelect: (node: FileNode) => void;
  onInsert: (path: string) => void;
  onDiff: (path: string) => void;
  onHistory: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const isFolder = node.type === 'folder';

  return (
    <div>
      <div
        className={cn(
          'group flex items-center gap-1.5 rounded-md px-2 py-[4px] text-xs text-foreground-muted transition-colors',
          selectedPath === node.path ? 'bg-primary/10 text-foreground ring-1 ring-primary/30' : 'hover:bg-white/[0.04] hover:text-foreground',
        )}
        style={{ paddingLeft: `${depth * 13 + 8}px` }}
      >
        <button
          type="button"
          className="min-w-0 flex flex-1 items-center gap-1.5 text-left"
          onClick={() => {
            if (isFolder) setExpanded((value) => !value);
            onSelect(node);
          }}
        >
          {isFolder ? (
            <Folder className="h-3.5 w-3.5 shrink-0 text-primary" />
          ) : (
            <FileText className="h-3.5 w-3.5 shrink-0 text-foreground-subtle" />
          )}
          <span className="min-w-0 flex-1 truncate">{node.name}</span>
        </button>
        {node.gitStatus && node.gitStatus !== 'clean' && (
          <span className={cn('rounded px-1 text-[9px] font-semibold', gitBadgeClass(node.gitStatus))}>
            {gitBadge[node.gitStatus]}
          </span>
        )}
        {!isFolder && (
          <div className="hidden items-center gap-0.5 group-hover:flex">
            <button className="rounded p-0.5 hover:bg-white/10" title="插入聊天" onClick={() => onInsert(node.path)}>
              <Copy className="h-3 w-3" />
            </button>
            <button className="rounded p-0.5 hover:bg-white/10" title="查看 Diff" onClick={() => onDiff(node.path)}>
              <GitCompare className="h-3 w-3" />
            </button>
            <button className="rounded p-0.5 hover:bg-white/10" title="查看历史" onClick={() => onHistory(node.path)}>
              <History className="h-3 w-3" />
            </button>
          </div>
        )}
      </div>
      {isFolder && expanded && node.children?.map((child) => (
        <FileTreeNode
          key={child.id}
          node={child}
          depth={depth + 1}
          selectedPath={selectedPath}
          onSelect={onSelect}
          onInsert={onInsert}
          onDiff={onDiff}
          onHistory={onHistory}
        />
      ))}
    </div>
  );
}

function PreviewPane({ preview }: { preview: WorkspaceFilePreview | null }) {
  if (!preview) {
    return <div className="p-3 text-xs text-foreground-subtle">选择文件以预览。</div>;
  }

  return (
    <div className="overflow-hidden rounded-lg border border-white/10 bg-background/70">
      <div className="border-b border-white/10 px-3 py-2 text-[11px] text-foreground-subtle">
        <div className="truncate font-medium text-foreground">{preview.path}</div>
        <div className="mt-0.5 flex flex-wrap gap-2">
          {preview.size !== undefined && <span>{formatBytes(preview.size)}</span>}
          {preview.mime_type && <span>{preview.mime_type}</span>}
          {preview.truncated && <span className="text-warning">已截断</span>}
        </div>
      </div>
      {preview.type === 'text' ? (
        <pre className="max-h-[260px] overflow-auto p-3 text-[11px] leading-5 text-foreground-muted">{preview.content || ''}</pre>
      ) : preview.type === 'image' && preview.content ? (
        <div className="max-h-[260px] overflow-auto p-3">
          <img className="max-w-full rounded-md" src={`data:${preview.mime_type};base64,${preview.content}`} alt={preview.path} />
        </div>
      ) : preview.type === 'folder' ? (
        <div className="p-3 text-xs text-foreground-muted">{preview.children?.length ?? 0} 个子项</div>
      ) : (
        <div className="flex items-center gap-2 p-3 text-xs text-foreground-muted">
          {preview.type === 'image' ? <Image className="h-4 w-4" /> : <FileText className="h-4 w-4" />}
          {preview.type === 'pdf' ? 'PDF 预览占位' : preview.type === 'office' ? 'Office 文件预览占位' : '二进制文件'}
        </div>
      )}
    </div>
  );
}

function DiffPane({ diff }: { diff: GitDiffResult | null }) {
  if (!diff) return <div className="p-3 text-xs text-foreground-subtle">点击 Diff 查看当前改动。</div>;
  if (!diff.is_git_repo) return <div className="p-3 text-xs text-foreground-subtle">当前 Workspace 不是 Git 仓库。</div>;
  if (diff.error) return <div className="p-3 text-xs text-error">{diff.error}</div>;

  return (
    <div className="space-y-2">
      <div className="text-[11px] text-foreground-subtle">
        {diff.files.length} files changed · <span className="text-success">+{diff.additions ?? 0}</span>{' '}
        <span className="text-error">-{diff.deletions ?? 0}</span>
      </div>
      {diff.files.length === 0 ? (
        <div className="rounded-lg border border-white/10 p-3 text-xs text-foreground-subtle">没有 diff。</div>
      ) : diff.files.map((file) => (
        <details key={file.path} className="rounded-lg border border-white/10 bg-background/70" open={diff.files.length === 1}>
          <summary className="cursor-pointer px-3 py-2 text-xs text-foreground">
            {file.path} <span className="text-success">+{file.additions}</span> <span className="text-error">-{file.deletions}</span>
          </summary>
          <pre className="max-h-[260px] overflow-auto border-t border-white/10 p-3 text-[11px] leading-5 text-foreground-muted">{file.patch}</pre>
        </details>
      ))}
    </div>
  );
}

function HistoryPane({ history }: { history: GitHistoryResult | null }) {
  if (!history) return <div className="p-3 text-xs text-foreground-subtle">点击 History 查看提交历史。</div>;
  if (!history.is_git_repo) return <div className="p-3 text-xs text-foreground-subtle">当前 Workspace 不是 Git 仓库。</div>;
  if (history.error) return <div className="p-3 text-xs text-error">{history.error}</div>;
  return (
    <div className="space-y-2">
      {(history.commits ?? []).map((commit) => (
        <div key={commit.hash} className="rounded-lg border border-white/10 bg-background/70 px-3 py-2">
          <div className="truncate text-xs text-foreground">{commit.message}</div>
          <div className="mt-1 flex items-center gap-2 text-[10px] text-foreground-subtle">
            <span className="font-mono">{commit.short_hash}</span>
            <span>{commit.author}</span>
            <span>{commit.date}</span>
          </div>
        </div>
      ))}
      {(history.commits ?? []).length === 0 && <div className="text-xs text-foreground-subtle">没有历史记录。</div>}
    </div>
  );
}

export function WorkspacePanel({ currentConversationId }: { currentConversationId: string | null }) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const {
    fileTree,
    loading,
    loaded,
    workspaces,
    activeWorkspaceId,
    gitStatus,
    loadWorkspaceList,
    selectWorkspace,
    refreshActiveWorkspace,
    openActiveWorkspace,
  } = useWorkspaceStore();
  const inputText = useChatStore((state) => state.inputText);
  const setInputText = useChatStore((state) => state.setInputText);
  const openFile = useWorkbenchStore((state) => state.openFile);
  const [selectedPath, setSelectedPath] = useState('');
  const [preview, setPreview] = useState<WorkspaceFilePreview | null>(null);
  const [diff, setDiff] = useState<GitDiffResult | null>(null);
  const [history, setHistory] = useState<GitHistoryResult | null>(null);
  const [mode, setMode] = useState<PanelMode>('preview');
  const [busy, setBusy] = useState(false);

  const dirtyCount = useMemo(
    () => [
      ...(gitStatus?.staged ?? []),
      ...(gitStatus?.modified ?? []),
      ...(gitStatus?.untracked ?? []),
      ...(gitStatus?.deleted ?? []),
      ...(gitStatus?.conflicts ?? []),
    ].length,
    [gitStatus],
  );

  useEffect(() => {
    void loadWorkspaceList();
  }, [loadWorkspaceList]);

  const activeId = activeWorkspaceId ?? currentConversationId ?? '';

  const selectFile = async (node: FileNode) => {
    setSelectedPath(node.path);
    setMode('preview');
    if (!activeId) return;
    if (node.type === 'file') {
      // Open the file as an editable workbench tab.
      void openFile(activeId, node.path);
    }
    setBusy(true);
    try {
      setPreview(await previewWorkspaceFile(activeId, node.path));
    } finally {
      setBusy(false);
    }
  };

  const insertPath = (path: string) => {
    setInputText(`${inputText}${inputText.endsWith(' ') || !inputText ? '' : ' '}\`${path}\``);
  };

  const loadDiff = async (path?: string) => {
    if (!activeId) return;
    setMode('diff');
    setBusy(true);
    try {
      setDiff(await getWorkspaceGitDiff(activeId, { scope: path ? 'file' : 'working', filePath: path }));
    } finally {
      setBusy(false);
    }
  };

  const loadHistory = async (path?: string) => {
    if (!activeId) return;
    setMode('history');
    setBusy(true);
    try {
      setHistory(await getWorkspaceGitHistory(activeId, { mode: 'log', filePath: path, limit: 12 }));
    } finally {
      setBusy(false);
    }
  };

  const createItem = async (type: 'file' | 'folder') => {
    if (!activeId) return;
    const label = type === 'file' ? '新建文件路径' : '新建文件夹路径';
    const path = window.prompt(label, type === 'file' ? 'notes.md' : 'src/new-folder');
    if (!path) return;
    setBusy(true);
    try {
      await createWorkspaceItem(activeId, { path, type });
      await refreshActiveWorkspace();
    } finally {
      setBusy(false);
    }
  };

  const uploadFiles = async (files: FileList | null) => {
    if (!activeId || !files?.length) return;
    setBusy(true);
    try {
      await uploadWorkspaceFiles(activeId, Array.from(files));
      await refreshActiveWorkspace();
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden p-2">
      <div className="mb-2 rounded-xl border border-white/10 bg-[#202020] p-2">
        <div className="mb-2 flex items-center gap-2">
          <select
            value={activeId}
            onChange={(event) => {
              if (event.target.value) void selectWorkspace(event.target.value);
            }}
            className="min-w-0 flex-1 rounded-md border border-white/10 bg-background px-2 py-1 text-xs text-foreground outline-none"
          >
            {!activeId && <option value="">Workspace</option>}
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
            ))}
          </select>
          <button className="rounded-md p-1.5 text-foreground-muted hover:bg-white/[0.07] hover:text-foreground" title="刷新" onClick={() => void refreshActiveWorkspace()}>
            <RefreshCw className={cn('h-3.5 w-3.5', (loading || busy) && 'animate-spin')} />
          </button>
          <button className="rounded-md p-1.5 text-foreground-muted hover:bg-white/[0.07] hover:text-foreground" title="打开目录" onClick={() => void openActiveWorkspace()}>
            <ExternalLink className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-foreground-subtle">
          <GitBranch className="h-3.5 w-3.5" />
          {gitStatus?.is_git_repo ? (
            <>
              <span className="truncate">{gitStatus.branch || 'HEAD'}</span>
              <span>·</span>
              <span className={gitStatus.is_dirty ? 'text-warning' : 'text-success'}>
                {gitStatus.is_dirty ? `${dirtyCount} modified` : 'Clean'}
              </span>
            </>
          ) : (
            <span>未初始化 Git</span>
          )}
        </div>
        <div className="mt-2 grid grid-cols-5 gap-1">
          <button className="workspace-action-btn" title="上传文件" onClick={() => inputRef.current?.click()}><Upload className="h-3.5 w-3.5" /></button>
          <button className="workspace-action-btn" title="新建文件" onClick={() => void createItem('file')}><FilePlus2 className="h-3.5 w-3.5" /></button>
          <button className="workspace-action-btn" title="新建文件夹" onClick={() => void createItem('folder')}><FolderPlus className="h-3.5 w-3.5" /></button>
          <button className="workspace-action-btn" title="Git Diff" onClick={() => void loadDiff()}><GitCompare className="h-3.5 w-3.5" /></button>
          <button className="workspace-action-btn" title="Git History" onClick={() => void loadHistory()}><Clock className="h-3.5 w-3.5" /></button>
        </div>
        <input ref={inputRef} type="file" multiple className="hidden" onChange={(event) => void uploadFiles(event.target.files)} />
      </div>

      <div className="min-h-[170px] flex-1 overflow-y-auto rounded-lg border border-white/5 bg-background/30 p-1">
        {!activeId ? (
          <p className="p-2 text-xs text-foreground-subtle">{t('nav.workspace.empty')}</p>
        ) : loading ? (
          <div className="flex items-center gap-2 p-2 text-xs text-foreground-muted"><Loader2 className="h-3 w-3 animate-spin" />{t('nav.workspace.loading')}</div>
        ) : loaded && fileTree.length === 0 ? (
          <p className="p-2 text-xs text-foreground-subtle">{t('nav.workspace.noFiles')}</p>
        ) : (
          fileTree.map((node) => (
            <FileTreeNode
              key={node.id}
              node={node}
              selectedPath={selectedPath}
              onSelect={selectFile}
              onInsert={insertPath}
              onDiff={loadDiff}
              onHistory={loadHistory}
            />
          ))
        )}
      </div>

      <div className="mt-2 max-h-[42%] min-h-[170px] overflow-y-auto">
        <div className="mb-2 flex items-center gap-1">
          {(['preview', 'diff', 'history'] as PanelMode[]).map((item) => (
            <button
              key={item}
              className={cn('rounded-md px-2 py-1 text-[11px] transition-colors', mode === item ? 'bg-primary/15 text-primary' : 'text-foreground-subtle hover:bg-white/[0.05] hover:text-foreground')}
              onClick={() => setMode(item)}
            >
              {item === 'preview' ? 'Preview' : item === 'diff' ? 'Diff' : 'History'}
            </button>
          ))}
          {busy && <Loader2 className="ml-auto h-3.5 w-3.5 animate-spin text-foreground-subtle" />}
        </div>
        {mode === 'preview' && <PreviewPane preview={preview} />}
        {mode === 'diff' && <DiffPane diff={diff} />}
        {mode === 'history' && <HistoryPane history={history} />}
      </div>
    </div>
  );
}
