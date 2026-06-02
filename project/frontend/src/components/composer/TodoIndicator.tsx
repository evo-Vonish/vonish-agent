import { useState, useRef, useEffect } from 'react';
import { ListTodo, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chatStore';
import { useToolStore } from '@/stores/useToolStore';
import { useI18n } from '@/i18n';
import { latestTodoFromMessages } from '@/lib/todo';

export function TodoIndicator({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { t } = useI18n();

  // Collect todo from the latest message that has todo data
  const messages = useChatStore((s) => s.messages);
  const todo = latestTodoFromMessages(messages);

  const counts = { done: 0, doing: 0, todo: 0, blocked: 0, cancelled: 0 };
  if (todo?.items) {
    for (const it of todo.items) {
      const s = it.status as keyof typeof counts;
      if (s in counts) counts[s]++;
    }
  }
  const total = counts.done + counts.doing + counts.todo + counts.blocked + counts.cancelled;
  const done = counts.done + counts.cancelled;

  // Check if set_todo_list tool is enabled
  const tools = useToolStore((s) => s.tools);
  const todoToolEnabled = tools.some((t) => t.name === 'set_todo_list' && t.isEnabled !== false);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  const iconColors: Record<string, string> = {
    done: '#22c55e',
    doing: '#3b82f6',
    todo: '#6b7280',
    blocked: '#ef4444',
    cancelled: '#9ca3af',
  };

  return (
    <div ref={ref} className={cn('relative', className)}>
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs transition-colors',
          open
            ? 'bg-surface-hover text-foreground'
            : 'text-foreground-muted hover:text-foreground hover:bg-surface-hover'
        )}
        title={t('todo.title')}
      >
        <ListTodo className="w-3.5 h-3.5" />
        {total > 0 ? (
          <span className="tabular-nums">
            {done}/{total}
          </span>
        ) : todoToolEnabled ? (
          <span className="text-[10px]">{t('todo.empty')}</span>
        ) : (
          <AlertTriangle className="w-3.5 h-3.5 text-warning" />
        )}
      </button>

      {open && (
        <div className="absolute left-0 bottom-full mb-2 w-64 bg-surface-elevated border border-border rounded-xl shadow-2xl z-50 animate-in fade-in slide-in-from-bottom-2 duration-150 overflow-hidden">
          <div className="px-3 py-2 border-b border-border">
            <span className="text-xs font-semibold text-foreground">{t('todo.title')}</span>
          </div>

          <div className="p-3 max-h-[50vh] overflow-y-auto">
            {!todoToolEnabled ? (
              <div className="flex items-start gap-2 text-xs text-warning">
                <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{t('todo.disabledHint')}</span>
              </div>
            ) : total === 0 ? (
              <p className="text-xs text-foreground-subtle">{t('todo.noItems')}</p>
            ) : (
              <div className="space-y-2">
                {/* Mini progress bar */}
                {total > 0 && (
                  <div className="flex items-center gap-2 text-[10px] text-foreground-subtle">
                    <div className="flex-1 h-1.5 rounded-full bg-border overflow-hidden">
                      <div
                        className="h-full rounded-full bg-success transition-all"
                        style={{ width: `${(done / total) * 100}%` }}
                      />
                    </div>
                    <span>{done}/{total}</span>
                  </div>
                )}

                {/* Todo items */}
                <div className="space-y-1">
                  {todo!.items!.map((it) => (
                    <div
                      key={it.id}
                      className="flex items-center gap-2 text-xs rounded-md px-1.5 py-1 hover:bg-surface-hover transition-colors"
                    >
                      <span
                        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: iconColors[it.status] || '#6b7280' }}
                      />
                      <span
                        className={cn(
                          'flex-1 truncate',
                          it.status === 'done' || it.status === 'cancelled'
                            ? 'line-through text-foreground-subtle'
                            : it.status === 'doing'
                              ? 'text-primary font-medium'
                              : 'text-foreground-muted'
                        )}
                      >
                        {it.title}
                      </span>
                      <span className="text-[10px] text-foreground-subtle flex-shrink-0">
                        {it.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
