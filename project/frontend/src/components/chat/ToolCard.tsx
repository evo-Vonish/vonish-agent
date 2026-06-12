import type { ElementType, ReactNode } from 'react';
import {
  Archive,
  Brain,
  Camera,
  Check,
  CheckCircle2,
  ChevronRight,
  Clock,
  Copy,
  Cpu,
  ExternalLink,
  FilePlus,
  FileText,
  FolderSearch,
  FolderTree,
  GitBranch,
  GitCompare,
  Globe,
  History,
  Keyboard,
  ListChecks,
  Loader2,
  MessageSquareQuote,
  MousePointerClick,
  Pencil,
  RotateCcw,
  ScrollText,
  Search,
  ShieldAlert,
  Sparkles,
  Terminal,
  Trash2,
  Wrench,
  X,
  XCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ToolCall } from '@/types';
import { formatDuration } from '@/lib/utils';
import { ExecutionCollapse } from './ExecutionCollapse';
import { SmoothStreamingText } from './SmoothStreamingText';
import { useExecutionDisclosure } from './useExecutionDisclosure';
import { useInlinePromptStore } from '@/stores/inlinePromptStore';
import { useReferenceStore, type NewReference } from '@/stores/referenceStore';
import { elementPopoverPosition } from '@/lib/selectionRef';

interface ToolCardProps {
  tool: ToolCall;
  className?: string;
}

const toolIconMap: Record<string, ElementType> = {
  browser_open: Globe,
  browser_snapshot: Camera,
  browser_click: MousePointerClick,
  browser_input: Keyboard,
  browser_scroll: ScrollText,
  browser_wait: Clock,
  browser_screenshot: Camera,
  browser_close: X,
  web_search: Search,
  search_web: Search,
  web_fetch: FileText,
  fetch_url: FileText,
  deep_research: Search,
  github_search: GitBranch,
  image_search: Search,
  read_file: FileText,
  file_read: FileText,
  write_file: FilePlus,
  write_to_file: FilePlus,
  edit_file: Pencil,
  apply_patch: Pencil,
  delete_file: Trash2,
  search_workspace: FolderSearch,
  list_directory: FolderTree,
  list_files: FolderTree,
  snapshot: FolderTree,
  git_status: GitBranch,
  git_diff: GitCompare,
  git_history: History,
  git_commit: CheckCircle2,
  git_restore: RotateCcw,
  set_todo_list: ListChecks,
  list_artifact_skills: Sparkles,
  read_artifact_skill: ScrollText,
  skill_activate: Sparkles,
  approval_request: ShieldAlert,
  request_approval: ShieldAlert,
  ask_user_question: ShieldAlert,
  model_call: Cpu,
  context_compact: Archive,
  shell_command: Terminal,
  bash: Terminal,
  ipython: Terminal,
  thinking: Brain,
};

const statusConfig: Record<ToolCall['status'], { color: string; icon: ReactNode; label: string; title: string }> = {
  pending: {
    color: '#5c5855',
    icon: <Clock className="h-3.5 w-3.5" />,
    label: '等待中',
    title: '等待调用工具',
  },
  running: {
    color: '#c66a38',
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
    label: '执行中',
    title: '正在调用工具',
  },
  success: {
    color: '#5a8a5e',
    icon: <Check className="h-3.5 w-3.5" />,
    label: '已完成',
    title: '已调用工具',
  },
  error: {
    color: '#a85450',
    icon: <XCircle className="h-3.5 w-3.5" />,
    label: '失败',
    title: '工具调用失败',
  },
};

function compactJson(value: unknown) {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function titleForTool(name: string) {
  const map: Record<string, string> = {
    shell_command: 'Shell',
    ipython: 'iPython',
    web_search: 'Web Search',
    search_web: 'Web Search',
    web_fetch: 'Web Fetch',
    fetch_url: 'Web Fetch',
    deep_research: 'Deep Research',
    read_file: 'Read File',
    file_read: 'Read File',
    write_file: 'Write File',
    write_to_file: 'Write File',
    edit_file: 'Edit File',
    apply_patch: 'Apply Patch',
    delete_file: 'Delete File',
    search_workspace: 'Search Workspace',
    list_directory: 'List Directory',
    snapshot: 'Snapshot',
    set_todo_list: 'Task List',
    list_artifact_skills: 'Artifact Skills',
    read_artifact_skill: 'Read Artifact Skill',
    git_status: 'Git Status',
    git_diff: 'Git Diff',
    git_history: 'Git History',
  };
  return map[name] ?? name;
}

function panelTitle(name: string) {
  if (name === 'shell_command') return 'Shell';
  if (name === 'ipython') return 'Python';
  if (name.startsWith('git_')) return 'Git';
  if (name.startsWith('web_') || name.includes('search') || name.includes('fetch')) return 'Web';
  return 'Tool';
}

function resultObject(result: unknown): Record<string, unknown> | null {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return null;
  return result as Record<string, unknown>;
}

function extractSearchResults(result: unknown) {
  if (Array.isArray(result)) {
    return result
      .filter((item) => item && typeof item === 'object')
      .slice(0, 8)
      .map((item) => {
        const record = item as Record<string, unknown>;
        return {
          title: String(record.title ?? record.name ?? record.url ?? 'Untitled'),
          url: String(record.url ?? record.link ?? ''),
          snippet: String(record.snippet ?? record.summary ?? record.content ?? record.text ?? ''),
        };
      });
  }
  const data = resultObject(result);
  const candidates = [
    data?.results,
    data?.items,
    data?.hits,
    data?.data,
  ].find(Array.isArray) as Array<Record<string, unknown>> | undefined;
  return (candidates ?? [])
    .filter((item) => item && typeof item === 'object')
    .slice(0, 8)
    .map((item) => ({
      title: String(item.title ?? item.name ?? item.url ?? 'Untitled'),
      url: String(item.url ?? item.link ?? ''),
      snippet: String(item.snippet ?? item.summary ?? item.content ?? item.text ?? ''),
    }));
}

function SearchResultView({ result }: { result: unknown }) {
  const items = extractSearchResults(result);
  if (!items.length) return null;
  return (
    <div className="space-y-1.5 py-1">
      {items.map((item, index) => (
        <div key={`${item.url}-${index}`} className="flex items-start gap-2 rounded-md px-1 py-1.5">
          <span className="mt-0.5 w-5 shrink-0 text-right font-mono-code text-[10.5px] text-[#5c5855]">
            {index + 1}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              {item.url ? (
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="truncate text-[12.5px] font-medium text-[#e8e6e3] hover:underline"
                  onClick={(event) => event.stopPropagation()}
                >
                  {item.title}
                </a>
              ) : (
                <span className="truncate text-[12.5px] font-medium text-[#e8e6e3]">{item.title}</span>
              )}
              {item.url && <ExternalLink className="h-2.5 w-2.5 shrink-0 text-[#5c5855]" />}
            </div>
            {item.url && (
              <div className="mt-0.5 truncate font-mono-code text-[10.5px] text-primary/75">
                {item.url.replace(/^https?:\/\//, '')}
              </div>
            )}
            {item.snippet && <p className="mt-1 text-[11.5px] leading-5 text-[#9a9590]">{item.snippet}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

function GitResultView({ tool }: { tool: ToolCall }) {
  const data = resultObject(tool.result);
  if (!data || !tool.name.startsWith('git_')) return null;
  if (data.is_git_repo === false) {
    return <div className="rounded-md bg-white/[0.035] px-3 py-2 text-xs text-[#9a9590]">当前 Workspace 不是 Git 仓库。</div>;
  }
  if (tool.name === 'git_status') {
    const rows = ['staged', 'modified', 'untracked', 'deleted', 'conflicts']
      .flatMap((key) => (Array.isArray(data[key]) ? (data[key] as string[]).map((path) => ({ key, path })) : []));
    return (
      <div className="space-y-1.5 rounded-md bg-white/[0.035] px-3 py-2 text-xs">
        <div className="text-[#e8e6e3]">{String(data.branch ?? 'HEAD')} · {rows.length ? `${rows.length} changed` : 'Clean'}</div>
        {rows.slice(0, 20).map((row) => (
          <div key={`${row.key}-${row.path}`} className="flex gap-2 text-[#9a9590]">
            <span className="w-16 text-[#5c5855]">{row.key}</span>
            <span className="min-w-0 truncate">{row.path}</span>
          </div>
        ))}
      </div>
    );
  }
  if (tool.name === 'git_diff') {
    const files = Array.isArray(data.files) ? data.files as Array<Record<string, unknown>> : [];
    return (
      <div className="space-y-2 text-xs">
        <div className="text-[#9a9590]">
          {files.length} files changed · <span className="text-success">+{String(data.additions ?? 0)}</span>{' '}
          <span className="text-error">-{String(data.deletions ?? 0)}</span>
        </div>
        {files.slice(0, 5).map((file) => (
          <details key={String(file.path)} className="rounded-md bg-white/[0.035]" open={files.length === 1}>
            <summary className="cursor-pointer px-3 py-2 text-[#e8e6e3]">
              {String(file.path)} <span className="text-success">+{String(file.additions ?? 0)}</span>{' '}
              <span className="text-error">-{String(file.deletions ?? 0)}</span>
            </summary>
            <pre className="max-h-56 overflow-auto border-t border-white/[0.055] px-3 py-2 font-mono text-[11px] text-[#9a9590]">
              {String(file.patch ?? '')}
            </pre>
          </details>
        ))}
      </div>
    );
  }
  return null;
}

function ArtifactSkillResultView({ result }: { result: unknown }) {
  const data = resultObject(result);
  if (!data?.artifact_skill) return null;
  const files = Array.isArray(data.files_read) ? data.files_read as Array<Record<string, unknown>> : [];
  const missing = Array.isArray(data.missing_files) ? data.missing_files.map(String) : [];
  const display = resultObject(data.display);
  return (
    <div className="space-y-3 rounded-md bg-white/[0.035] px-3 py-3 text-xs">
      <div>
        <div className="text-[13px] font-semibold text-[#e8e6e3]">
          {String(display?.title ?? `Read ${String(data.skill ?? 'artifact').toUpperCase()} skill`)}
        </div>
        <div className="mt-1 leading-5 text-[#9a9590]">
          {String(display?.summary ?? `Loaded ${files.length} skill files.`)}
        </div>
      </div>
      <div className="grid gap-1.5 sm:grid-cols-2">
        {files.map((file) => (
          <div key={String(file.path ?? file.name)} className="flex min-w-0 items-center gap-2 rounded border border-white/[0.06] bg-black/10 px-2 py-1.5">
            <ScrollText className="h-3.5 w-3.5 shrink-0 text-[#c66a38]" />
            <span className="min-w-0 flex-1 truncate text-[#d8d4cf]">{String(file.name ?? 'skill file')}</span>
            <span className="shrink-0 font-mono-code text-[10.5px] text-[#5c5855]">{String(file.chars ?? 0)} chars</span>
          </div>
        ))}
      </div>
      {missing.length > 0 && (
        <div className="rounded border border-[#a85450]/25 bg-[#3d1f1a]/35 px-2 py-1.5 text-[#d9948f]">
          缺失参考：{missing.join(', ')}
        </div>
      )}
      <div className="text-[11px] leading-5 text-[#5c5855]">
        Skill 原文已进入模型上下文；前端仅显示读取摘要，避免长文档占满工具卡片。
      </div>
    </div>
  );
}

function DefaultResultView({ tool }: { tool: ToolCall }) {
  if (tool.name === 'read_artifact_skill') {
    return <ArtifactSkillResultView result={tool.result} />;
  }
  const searchView = (tool.name.includes('search') || tool.name === 'web_fetch') ? <SearchResultView result={tool.result} /> : null;
  const gitView = <GitResultView tool={tool} />;
  if (searchView || gitView) {
    return (
      <div className="space-y-2">
        {searchView}
        {gitView}
      </div>
    );
  }
  return null;
}

function hasStructuredResult(tool: ToolCall) {
  if (tool.name === 'read_artifact_skill' && resultObject(tool.result)?.artifact_skill) return true;
  if (tool.name.startsWith('git_') && resultObject(tool.result)) return true;
  if ((tool.name.includes('search') || tool.name === 'web_fetch') && extractSearchResults(tool.result).length > 0) return true;
  return false;
}

export function ToolCard({ tool, className }: ToolCardProps) {
  const disclosure = useExecutionDisclosure({
    id: tool.id,
    status: tool.status,
    defaultExpanded: tool.status === 'running' || tool.status === 'error',
    runningStatuses: ['running'],
    failedStatuses: ['error'],
    terminalStatuses: ['success', 'error'],
  });
  const expanded = disclosure.expanded;
  const config = statusConfig[tool.status];
  const Icon = toolIconMap[tool.name] ?? Wrench;
  const title = titleForTool(tool.name);
  const showStructuredResult = hasStructuredResult(tool);
  const structuredResult = showStructuredResult ? <DefaultResultView tool={tool} /> : null;
  const argsText = compactJson(tool.arguments);
  const resultText = compactJson(tool.result);
  const addReference = useReferenceStore((state) => state.addReference);
  const openPrompt = useInlinePromptStore((state) => state.openPrompt);
  const fullText = [title, argsText, resultText, tool.error].filter(Boolean).join('\n\n');
  const draft: NewReference = {
    sourceType: 'artifact-block',
    sourceId: tool.id,
    title: `Tool · ${title}`,
    preview: fullText.slice(0, 4000),
    location: { blockId: tool.id, blockType: 'tool' },
    payload: { tool },
  };

  return (
    <div className={cn('relative space-y-1.5 pl-9', className)} style={{ color: config.color }}>
      {expanded && (
        <span
          className={cn(
            'workflow-rail-line workflow-rail-line-short',
            tool.status === 'running' && 'workflow-rail-line-running',
            tool.status === 'error' && 'workflow-rail-line-error',
          )}
        />
      )}
      <span
        className={cn(
          'workflow-rail-icon',
          tool.status === 'running' && 'workflow-rail-icon-running',
          tool.status === 'error' && 'workflow-rail-icon-error',
        )}
      >
        {tool.status === 'running' ? <Loader2 className="h-4 w-4 animate-spin" /> : tool.status === 'error' ? <XCircle className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
      </span>
      <div className="group flex max-w-full items-center gap-2">
        <button
          type="button"
          onClick={() => disclosure.toggle()}
          className={cn(
            'flex min-w-0 items-center gap-2 rounded-md py-0.5 text-left text-[14px] font-medium transition-colors',
            tool.status === 'error' ? 'text-error hover:text-error' : 'text-[#9a9590] hover:text-[#e8e6e3]',
          )}
        >
          <span
            className="execution-title min-w-0 truncate"
            data-motion={disclosure.titleMotion}
            data-tone={disclosure.tone}
            data-kind={tool.name === 'shell_command' || tool.name === 'ipython' ? 'command' : tool.name.startsWith('web_') ? 'web' : 'tool'}
          >
            <SmoothStreamingText text={config.title} active={tool.status === 'running'} />
            <span className="ml-1 text-[#5c5855]">{title}</span>
          </span>
          {tool.duration !== undefined && (
            <span className="shrink-0 font-mono-code text-[12px] text-[#5c5855]">
              {formatDuration(tool.duration)}
            </span>
          )}
          <ChevronRight
            className="h-3.5 w-3.5 shrink-0 text-[#5c5855] transition-transform duration-200 group-hover:text-[#9a9590]"
            style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
          />
        </button>
        <span className="hidden shrink-0 items-center gap-0.5 group-hover:flex group-focus-within:flex" data-quote-card="tool">
          <button type="button" onClick={() => addReference(draft)} className="rounded p-0.5 text-[#5c5855] hover:bg-white/5 hover:text-[#e8e6e3]" title="引用完整工具">
            <MessageSquareQuote className="h-3.5 w-3.5" />
          </button>
          <button type="button" onClick={(event) => openPrompt(draft, elementPopoverPosition(event.currentTarget, 340, 150))} className="rounded p-0.5 text-[#5c5855] hover:bg-white/5 hover:text-[#e0a072]" title="询问 AI">
            <Sparkles className="h-3.5 w-3.5" />
          </button>
          <button type="button" onClick={() => void navigator.clipboard?.writeText(fullText).catch(() => {})} className="rounded p-0.5 text-[#5c5855] hover:bg-white/5 hover:text-[#e8e6e3]" title="复制完整工具">
            <Copy className="h-3.5 w-3.5" />
          </button>
        </span>
      </div>
      <ExecutionCollapse open={expanded}>
        <div
          className="codex-panel-reveal codex-detail-panel relative overflow-hidden rounded-md text-[13px] shadow-sm"
          style={{
            background: 'rgba(20, 20, 22, 0.68)',
            border: tool.status === 'error' ? '1px solid rgba(168,84,80,0.24)' : '1px solid rgba(255,255,255,0.06)',
          }}
        >
          <div className="flex items-center gap-2 border-b border-white/[0.055] px-3 py-2 text-sm text-[#9a9590]">
            <Icon className="h-3.5 w-3.5" style={{ color: config.color }} />
            <span className="min-w-0 flex-1 truncate font-mono-code text-[12px] tracking-[0.02em]">{panelTitle(tool.name)}</span>
            <span className="font-mono-code text-[11px]" style={{ color: config.color }}>{config.label}</span>
          </div>
          <div className="max-h-[360px] space-y-3 overflow-auto px-3 py-3 font-mono text-sm leading-6">
            {argsText && (
              <div>
                <span className="font-mono-code text-[10.5px] uppercase tracking-[0.08em] text-[#5c5855]">参数</span>
                <pre className="mt-1 whitespace-pre-wrap break-words text-[#9a9590]">{argsText}</pre>
              </div>
            )}
            {tool.result !== undefined && (
              <div>
                <span className="font-mono-code text-[10.5px] uppercase tracking-[0.08em] text-[#5c5855]">结果</span>
                <div className="mt-1">{structuredResult}</div>
                {!showStructuredResult && <pre className="mt-1 whitespace-pre-wrap break-words text-[#9a9590]">{resultText}</pre>}
              </div>
            )}
            {tool.error && (
              <div>
                <span className="font-mono-code text-[10.5px] uppercase tracking-[0.08em] text-error/70">错误</span>
                <pre className="mt-1 whitespace-pre-wrap break-words text-error">{tool.error}</pre>
              </div>
            )}
            {!argsText && tool.result === undefined && !tool.error && (
              <span className="text-[#5c5855]">无输出</span>
            )}
          </div>
          <div className={cn('flex items-center justify-end gap-2 px-3 pb-2 text-sm', tool.status === 'error' ? 'text-error' : 'text-[#9a9590]')}>
            {config.icon}
            <span>{config.label}</span>
          </div>
        </div>
      </ExecutionCollapse>
    </div>
  );
}
