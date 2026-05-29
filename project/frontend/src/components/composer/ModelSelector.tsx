import { useState } from 'react';
import { ChevronDown, Check, Cpu } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chatStore';

interface ModelSelectorProps {
  className?: string;
}

export function ModelSelector({ className }: ModelSelectorProps) {
  const [open, setOpen] = useState(false);
  const { models, selectedModelId, setSelectedModel } = useChatStore();
  const selected = models.find((m) => m.id === selectedModelId);

  return (
    <div className={cn('relative', className)}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2 py-1 rounded-md hover:bg-surface-hover text-foreground-muted hover:text-foreground transition-colors text-xs"
      >
        <Cpu className="w-3.5 h-3.5" />
        <span className="max-w-[100px] truncate">{selected?.name ?? '选择模型'}</span>
        <ChevronDown className={cn('w-3 h-3 transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute left-0 bottom-full mb-1 z-50 w-56 bg-surface-elevated border border-border rounded-lg shadow-xl py-1">
            {models.map((model) => (
              <button
                key={model.id}
                onClick={() => {
                  setSelectedModel(model.id);
                  setOpen(false);
                }}
                className={cn(
                  'w-full flex items-center gap-2 px-3 py-2 text-xs transition-colors text-left',
                  selectedModelId === model.id
                    ? 'bg-primary/10 text-foreground'
                    : 'text-foreground-muted hover:bg-surface-hover hover:text-foreground'
                )}
              >
                <Cpu className="w-3.5 h-3.5 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{model.name}</div>
                  <div className="text-[10px] opacity-50 truncate">{model.description}</div>
                </div>
                {selectedModelId === model.id && <Check className="w-3.5 h-3.5 text-primary flex-shrink-0" />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
