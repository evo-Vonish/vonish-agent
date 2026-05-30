import { useState } from 'react';
import { Plus, Wrench, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useToolStore } from '@/stores/useToolStore';
import { ToolCategorySection } from '@/components/tools/ToolCategorySection';
import { AddToolModal } from '@/components/tools/AddToolModal';
import type { ToolCategoryType } from '@/types/tools';

const CATEGORY_ORDER: ToolCategoryType[] = ['file_ops', 'workspace', 'python_ops', 'web_search', 'system'];

export default function ToolsPage() {
  const [showAddModal, setShowAddModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const tools = useToolStore((s) => s.tools);
  const enabledCount = tools.filter((t) => t.isEnabled).length;
  const totalCount = tools.length;

  // Filter categories based on search
  const visibleCategories = searchQuery.trim()
    ? CATEGORY_ORDER.filter((cat) => {
        const catTools = tools.filter(
          (t) =>
            t.category === cat &&
            (t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
              t.description.toLowerCase().includes(searchQuery.toLowerCase()))
        );
        return catTools.length > 0;
      })
    : CATEGORY_ORDER;

  return (
    <div className="h-full flex flex-col bg-background overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-border bg-surface">
        <div className="flex items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <Wrench className="w-4 h-4 text-primary" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-foreground">Tool Management</h1>
              <p className="text-[11px] text-foreground-muted">
                {enabledCount} of {totalCount} tools enabled
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Search */}
            <div className="relative hidden sm:block">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground-subtle" />
              <input
                type="text"
                placeholder="Search tools..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-56 pl-8 pr-3 py-1.5 text-xs rounded-lg bg-background border border-border text-foreground placeholder:text-foreground-subtle focus:outline-none focus:border-primary/50 transition-colors"
              />
            </div>

            {/* Add Tool button */}
            <button
              onClick={() => setShowAddModal(true)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors',
                'bg-primary text-white hover:bg-primary-hover'
              )}
            >
              <Plus className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Add Tool</span>
            </button>
          </div>
        </div>

        {/* Stats bar */}
        <div className="flex items-center gap-6 px-5 pb-3">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-success" />
            <span className="text-[11px] text-foreground-muted">
              {tools.filter((t) => t.approvalLevel === 'auto').length} Auto
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-warning" />
            <span className="text-[11px] text-foreground-muted">
              {tools.filter((t) => t.approvalLevel === 'suggest').length} Suggest
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-error" />
            <span className="text-[11px] text-foreground-muted">
              {tools.filter((t) => t.approvalLevel === 'required').length} Required
            </span>
          </div>
        </div>

        {/* Mobile search */}
        <div className="sm:hidden px-5 pb-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground-subtle" />
            <input
              type="text"
              placeholder="Search tools..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg bg-background border border-border text-foreground placeholder:text-foreground-subtle focus:outline-none focus:border-primary/50 transition-colors"
            />
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-5 space-y-8">
        {visibleCategories.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-foreground-subtle">
            <Search className="w-8 h-8 mb-3 opacity-40" />
            <p className="text-sm">No tools match your search</p>
          </div>
        ) : (
          visibleCategories.map((category) => (
            <ToolCategorySection key={category} category={category} />
          ))
        )}
      </div>

      {/* Add Tool Modal */}
      <AddToolModal open={showAddModal} onClose={() => setShowAddModal(false)} />
    </div>
  );
}
