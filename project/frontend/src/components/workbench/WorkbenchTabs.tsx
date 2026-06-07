import { Activity, Circle, FileCode, FileText, FileType2, Image as ImageIcon, Settings, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { isTabDirty, useWorkbenchStore, type WorkbenchTab } from '@/stores/workbenchStore';

function tabIcon(tab: WorkbenchTab) {
  if (tab.type === 'state') return Activity;
  if (tab.type === 'settings') return Settings;
  switch (tab.kind) {
    case 'image': return ImageIcon;
    case 'pdf':
    case 'office': return FileType2;
    case 'markdown': return FileText;
    default: return FileCode;
  }
}

export function WorkbenchTabs({ onRequestClose }: { onRequestClose: (tab: WorkbenchTab) => void }) {
  const tabs = useWorkbenchStore((s) => s.tabs);
  const activeTabId = useWorkbenchStore((s) => s.activeTabId);
  const setActiveTab = useWorkbenchStore((s) => s.setActiveTab);

  return (
    <div className="flex min-w-0 flex-1 items-stretch overflow-x-auto">
      {tabs.map((tab) => {
        const Icon = tabIcon(tab);
        const active = tab.id === activeTabId;
        const dirty = isTabDirty(tab);
        const closable = tab.type !== 'state';
        return (
          <div
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'group flex shrink-0 cursor-pointer items-center gap-1.5 border-r border-white/[0.06] px-3 text-[12px] transition-colors',
              active ? 'bg-white/[0.05] text-[#e8e6e3]' : 'text-[#5c5855] hover:bg-white/[0.025] hover:text-[#9a9590]',
            )}
            title={tab.path ?? tab.title}
          >
            <Icon className="h-3.5 w-3.5 shrink-0" />
            <span className="max-w-[160px] truncate">{tab.title}</span>
            {closable ? (
              <button
                type="button"
                onClick={(event) => { event.stopPropagation(); onRequestClose(tab); }}
                className="ml-0.5 grid h-4 w-4 place-items-center rounded text-[#5c5855] transition-colors hover:bg-white/[0.1] hover:text-[#e8e6e3]"
                title="关闭标签页"
              >
                {dirty ? (
                  <>
                    <Circle className="h-2 w-2 fill-current group-hover:hidden" />
                    <X className="hidden h-3 w-3 group-hover:block" />
                  </>
                ) : (
                  <X className="h-3 w-3" />
                )}
              </button>
            ) : (
              dirty && <Circle className="h-2 w-2 fill-current" />
            )}
          </div>
        );
      })}
    </div>
  );
}
