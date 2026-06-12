import { BrainCircuit, ChevronDown, DatabaseZap, X } from 'lucide-react';
import { useContextToastStore } from '@/stores/contextToastStore';

const nf = new Intl.NumberFormat('zh-CN');

function formatTokens(value?: number) {
  const safe = Number.isFinite(value) ? Number(value) : 0;
  if (safe >= 1000) return `${(safe / 1000).toFixed(safe >= 10000 ? 0 : 1)}k`;
  return nf.format(safe);
}

function phaseLabel(phase: string) {
  if (phase === 'tool_results_appended') return '工具结果已入上下文';
  if (phase === 'context_built') return '上下文已构建';
  return phase || '上下文状态';
}

export function ContextToastHost() {
  const toast = useContextToastStore((state) => state.toast);
  const visible = useContextToastStore((state) => state.visible);
  const expanded = useContextToastStore((state) => state.expanded);
  const dismiss = useContextToastStore((state) => state.dismissContextToast);
  const toggleExpanded = useContextToastStore((state) => state.toggleContextToastExpanded);

  if (!toast || !visible) return null;

  const ratio = Math.max(0, Math.min(1, toast.usageRatio || toast.totalTokens / Math.max(toast.maxTokens, 1)));
  const componentEntries = Object.entries(toast.components ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);
  const memoryTokens = Number(toast.contextMemory?.tokens ?? 0);
  const compressedCount = Number(toast.compressedToolResults ?? 0);
  const appendedCount = toast.appendedToolResults?.length ?? 0;

  return (
    <div className="pointer-events-none fixed bottom-24 right-5 z-[80] w-[min(460px,calc(100vw-2rem))]">
      <div className="pointer-events-auto overflow-hidden rounded-xl border border-[#c66a38]/25 bg-[#151311]/92 shadow-[0_18px_70px_rgba(0,0,0,0.48),inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-2xl">
        <div className="flex items-start gap-3 px-4 py-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[#c66a38]/25 bg-[#241912] text-[#e49a69]">
            <DatabaseZap size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-[#f2eee9]">{phaseLabel(toast.phase)}</span>
              <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2 py-0.5 text-[11px] text-emerald-300">
                活跃
              </span>
              {compressedCount > 0 && (
                <span className="rounded-full border border-[#c66a38]/25 bg-[#c66a38]/12 px-2 py-0.5 text-[11px] text-[#f0b083]">
                  压缩 {compressedCount}
                </span>
              )}
            </div>
            <div className="mt-1 line-clamp-2 text-xs leading-5 text-[#c9c2ba]">{toast.summary}</div>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[#8f8982]">
              <span>{formatTokens(toast.totalTokens)} / {formatTokens(toast.maxTokens)} tokens</span>
              <span>Memory Map {formatTokens(memoryTokens)}</span>
              <span>{toast.messageCount ?? 0} messages</span>
              <span>{toast.toolCount ?? 0} tools</span>
              {appendedCount > 0 && <span>新增工具结果 {appendedCount}</span>}
            </div>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.08]">
              <div
                className="h-full rounded-full bg-gradient-to-r from-emerald-400 via-[#c66a38] to-[#d98b5a] transition-[width] duration-500 ease-out"
                style={{ width: `${Math.max(4, ratio * 100)}%` }}
              />
            </div>
          </div>
          <button
            type="button"
            onClick={toggleExpanded}
            className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[#aaa39b] transition hover:bg-white/[0.08] hover:text-[#f2eee9]"
            aria-label={expanded ? '收起上下文状态' : '展开上下文状态'}
          >
            <ChevronDown size={16} className={`transition-transform ${expanded ? 'rotate-180' : ''}`} />
          </button>
          <button
            type="button"
            onClick={dismiss}
            className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[#77716b] transition hover:bg-white/[0.08] hover:text-[#f2eee9]"
            aria-label="关闭上下文状态"
          >
            <X size={15} />
          </button>
        </div>

        {expanded && (
          <div className="border-t border-white/[0.07] px-4 pb-4 pt-3">
            <div className="mb-2 flex items-center gap-2 text-xs font-medium text-[#d9d2ca]">
              <BrainCircuit size={14} className="text-[#e49a69]" />
              实时上下文明细
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {componentEntries.map(([name, tokens]) => (
                <div key={name} className="rounded-lg border border-white/[0.06] bg-white/[0.035] px-3 py-2">
                  <div className="truncate text-[11px] text-[#8f8982]">{name}</div>
                  <div className="mt-0.5 text-sm font-semibold text-[#f2eee9]">{formatTokens(tokens)}</div>
                </div>
              ))}
            </div>
            {toast.contextMemory?.preview && (
              <pre className="mt-3 max-h-36 overflow-auto rounded-lg border border-white/[0.06] bg-black/28 p-3 text-[11px] leading-5 text-[#bdb5ad]">
                {toast.contextMemory.preview}
              </pre>
            )}
            <div className="mt-3 text-[11px] leading-5 text-[#8f8982]">
              策略：原文保留；常规上下文展示 tool result 的头部、关键段、尾部；需要完整内容时由 recall 工具注入主动回忆区。
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
