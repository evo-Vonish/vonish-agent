import { useState } from 'react';
import { Globe, User, Settings, Cpu, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';
import { Tooltip } from '@/components/ui/Tooltip';

interface StatusBarProps {
  className?: string;
}

export function StatusBar({ className }: StatusBarProps) {
  const { isMobile } = useUIStore();
  const { selectedModelId, models } = useChatStore();
  const selected = models.find((m) => m.id === selectedModelId);
  const [moreOpen, setMoreOpen] = useState(false);

  if (isMobile) {
    return (
      <footer
        className={cn(
          'h-9 flex items-center justify-between px-3 border-t border-border bg-background flex-shrink-0',
          className
        )}
      >
        <div className="flex items-center gap-1">
          <button
            onClick={() => setMoreOpen(!moreOpen)}
            className="flex items-center gap-1 px-2 py-1 rounded-full bg-surface border border-border text-[10px] text-foreground-muted hover:text-foreground transition-colors"
          >
            <ChevronUp className="w-3 h-3" />
            更多
          </button>
        </div>
        <div className="flex items-center gap-1">
          <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-surface border border-border text-[10px] text-foreground-muted">
            <Cpu className="w-3 h-3" />
            <span className="truncate max-w-[80px]">{selected?.name ?? '未选择'}</span>
          </div>
        </div>

        {moreOpen && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setMoreOpen(false)} />
            <div className="absolute left-2 right-2 bottom-12 bg-surface-elevated border border-border rounded-xl shadow-2xl z-50 p-2 space-y-1">
              <button className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-foreground-muted hover:bg-surface-hover hover:text-foreground transition-colors">
                <Globe className="w-3.5 h-3.5" />
                语言
              </button>
              <button className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-foreground-muted hover:bg-surface-hover hover:text-foreground transition-colors">
                <User className="w-3.5 h-3.5" />
                账户
              </button>
              <button className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-foreground-muted hover:bg-surface-hover hover:text-foreground transition-colors">
                <Settings className="w-3.5 h-3.5" />
                设置
              </button>
            </div>
          </>
        )}
      </footer>
    );
  }

  return (
    <footer
      className={cn(
        'h-8 flex items-center justify-between px-3 border-t border-border bg-background flex-shrink-0 z-20',
        className
      )}
    >
      <div className="flex items-center gap-2">
        <Tooltip content="当前语言">
          <button className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-surface border border-border text-[10px] text-foreground-muted hover:text-foreground hover:border-border-hover transition-colors">
            <Globe className="w-3 h-3" />
            中文
          </button>
        </Tooltip>
        <Tooltip content="账户">
          <button className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-surface border border-border text-[10px] text-foreground-muted hover:text-foreground hover:border-border-hover transition-colors">
            <User className="w-3 h-3" />
            未登录
          </button>
        </Tooltip>
      </div>

      <div className="flex items-center gap-2">
        <Tooltip content="当前模型">
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-surface border border-border text-[10px] text-foreground-muted">
            <Cpu className="w-3 h-3" />
            <span className="truncate max-w-[120px]">{selected?.name ?? '未选择'}</span>
          </div>
        </Tooltip>
        <Tooltip content="设置">
          <button
            onClick={() => useUIStore.getState().toggleRightPanel()}
            className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-surface border border-border text-[10px] text-foreground-muted hover:text-foreground hover:border-border-hover transition-colors"
          >
            <Settings className="w-3 h-3" />
            设置
          </button>
        </Tooltip>
      </div>
    </footer>
  );
}
