import { cn } from '@/lib/utils';
import { CheckCircle2, Circle, MinusCircle, AlertCircle, XCircle, Loader2 } from 'lucide-react';

export interface TodoItem {
  id: string;
  title: string;
  status: 'todo' | 'doing' | 'done' | 'blocked' | 'cancelled';
  note?: string;
  updated_at?: string;
}

interface TodoCardProps {
  items: TodoItem[];
  count?: number;
}

const STATUS_CONFIG = {
  todo:    { icon: Circle,        color: 'text-foreground-muted', label: 'Todo' },
  doing:   { icon: Loader2,       color: 'text-warning animate-spin', label: 'Doing' },
  done:    { icon: CheckCircle2,  color: 'text-success', label: 'Done' },
  blocked: { icon: AlertCircle,   color: 'text-error',   label: 'Blocked' },
  cancelled:{ icon: XCircle,       color: 'text-foreground-subtle line-through', label: 'Cancelled' },
};

export function TodoCard({ items, count }: TodoCardProps) {
  if (!items?.length) return null;

  const doneCount = items.filter(i => i.status === 'done').length;

  return (
    <div className="rounded-xl border border-border bg-surface-elevated/50 mb-2 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
        <span className="text-xs font-semibold text-foreground">Todo</span>
        <span className="text-[10px] text-foreground-muted">
          {doneCount}/{items.length} done
        </span>
      </div>
      <div className="px-3 py-2 space-y-0.5">
        {items.map((item) => {
          const cfg = STATUS_CONFIG[item.status];
          const Icon = cfg.icon;
          return (
            <div
              key={item.id}
              className={cn(
                'flex items-start gap-2 py-1.5 px-2 rounded-md transition-colors',
                item.status === 'done' && 'opacity-60',
                item.status === 'blocked' && 'bg-error/5',
              )}
            >
              <Icon className={cn('w-3.5 h-3.5 mt-0.5 flex-shrink-0', cfg.color)} />
              <div className="min-w-0">
                <p className={cn('text-xs', item.status === 'cancelled' && 'line-through text-foreground-subtle', item.status !== 'cancelled' && 'text-foreground')}>
                  {item.title}
                </p>
                {item.note && (
                  <p className="text-[10px] text-foreground-subtle mt-0.5">{item.note}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
