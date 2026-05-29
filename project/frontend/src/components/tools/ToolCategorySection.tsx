import { useState } from 'react';
import {
  FolderOpen,
  Globe,
  Terminal,
  ChevronDown,
  ChevronUp,
  Power,
  PowerOff,
} from 'lucide-react';
import { useShallow } from 'zustand/shallow';
import { cn } from '@/lib/utils';
import type { ToolCategoryType } from '@/types/tools';
import { CATEGORY_LABELS } from '@/types/tools';
import { useToolStore } from '@/stores/useToolStore';
import { ToolCard } from './ToolCard';

const CATEGORY_ICON_MAP: Record<ToolCategoryType, React.ComponentType<{ className?: string }>> = {
  file_ops: FolderOpen,
  workspace: LayoutIcon,
  web_search: Globe,
  system: Terminal,
};

function LayoutIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
      <line x1="3" x2="21" y1="9" y2="9" />
      <line x1="9" x2="9" y1="21" y2="9" />
    </svg>
  );
}

interface ToolCategorySectionProps {
  category: ToolCategoryType;
}

export function ToolCategorySection({ category }: ToolCategorySectionProps) {
  const [collapsed, setCollapsed] = useState(false);
  const tools = useToolStore(
    useShallow((s) => s.tools.filter((t) => t.category === category)),
  );
  const enableCategory = useToolStore((s) => s.enableCategory);
  const disableCategory = useToolStore((s) => s.disableCategory);

  const IconComponent = CATEGORY_ICON_MAP[category];
  const label = CATEGORY_LABELS[category];
  const enabledCount = tools.filter((t) => t.isEnabled).length;
  const totalCount = tools.length;
  const allEnabled = enabledCount === totalCount && totalCount > 0;
  const allDisabled = enabledCount === 0;

  const handleToggleAll = () => {
    if (allEnabled) {
      disableCategory(category);
    } else {
      enableCategory(category);
    }
  };

  if (tools.length === 0) return null;

  return (
    <div className="space-y-3">
      {/* Category header */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center gap-2 group"
        >
          <IconComponent className="w-4 h-4 text-foreground-muted group-hover:text-foreground transition-colors" />
          <h3 className="text-sm font-semibold text-foreground">{label}</h3>
          <span className="text-xs text-foreground-subtle">
            ({enabledCount}/{totalCount} tools)
          </span>
          <span className="text-foreground-subtle group-hover:text-foreground transition-colors">
            {collapsed ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronUp className="w-3.5 h-3.5" />
            )}
          </span>
        </button>

        <div className="flex items-center gap-2">
          {/* Status indicator */}
          {allDisabled ? (
            <span className="text-[10px] text-foreground-subtle">— all disabled</span>
          ) : allEnabled ? (
            <span className="text-[10px] text-success">— all enabled</span>
          ) : (
            <span className="text-[10px] text-warning">— partial</span>
          )}

          {/* Enable/Disable all button */}
          <button
            onClick={handleToggleAll}
            className={cn(
              'flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium transition-colors',
              allEnabled
                ? 'bg-error/10 text-error hover:bg-error/20'
                : 'bg-success/10 text-success hover:bg-success/20'
            )}
          >
            {allEnabled ? (
              <>
                <PowerOff className="w-3 h-3" />
                Disable All
              </>
            ) : (
              <>
                <Power className="w-3 h-3" />
                Enable All
              </>
            )}
          </button>
        </div>
      </div>

      {/* Tools list */}
      <div
        className={cn(
          'space-y-2 transition-all duration-300 ease-in-out overflow-hidden',
          collapsed ? 'max-h-0 opacity-0' : 'max-h-[2000px] opacity-100'
        )}
      >
        {tools.map((tool) => (
          <ToolCard key={tool.name} tool={tool} />
        ))}
      </div>
    </div>
  );
}
