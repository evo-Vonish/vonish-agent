import { useEffect, useState } from 'react';
import { PanelRightClose } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { isTabDirty, useWorkbenchStore, type WorkbenchTab } from '@/stores/workbenchStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { WorkbenchTabs } from './WorkbenchTabs';
import { FileRenderer } from './FileRenderer';
import { StatePanel } from './StatePanel';
import { SettingsTab } from './SettingsTab';
import { ConfirmCloseDialog } from './ConfirmCloseDialog';

/**
 * The right-side workbench: a VS Code-style tab strip plus the active tab's
 * renderer. File tabs are editable; the pinned "State" tab hosts the existing
 * diagnostics (State / Config / Workspace).
 */
export function WorkbenchPanel() {
  const tabs = useWorkbenchStore((s) => s.tabs);
  const activeTabId = useWorkbenchStore((s) => s.activeTabId);
  const closeTab = useWorkbenchStore((s) => s.closeTab);
  const saveTab = useWorkbenchStore((s) => s.saveTab);
  const setRightPanelOpen = useUIStore((s) => s.setRightPanelOpen);
  const autoSave = useSettingsStore((s) => s.autoSave);
  const [pendingClose, setPendingClose] = useState<WorkbenchTab | null>(null);

  const activeTab = tabs.find((t) => t.id === activeTabId) ?? null;

  const requestClose = (tab: WorkbenchTab) => {
    if (isTabDirty(tab)) setPendingClose(tab);
    else closeTab(tab.id);
  };

  // Ctrl/Cmd+S saves the active file tab. (Ctrl+W is intentionally not bound —
  // most browsers reserve it for closing the browser tab.)
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        if (activeTab && activeTab.type === 'file' && isTabDirty(activeTab)) {
          event.preventDefault();
          void saveTab(activeTab.id);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [activeTab, saveTab]);

  // Auto-save: debounce after edits.
  useEffect(() => {
    if (autoSave !== 'delay' || !activeTab || activeTab.type !== 'file' || !isTabDirty(activeTab)) return;
    const timer = window.setTimeout(() => { void saveTab(activeTab.id); }, 1200);
    return () => window.clearTimeout(timer);
  }, [autoSave, activeTab, saveTab]);

  // Auto-save: on window blur (focus change).
  useEffect(() => {
    if (autoSave !== 'blur') return;
    const onBlur = () => {
      useWorkbenchStore.getState().tabs.forEach((t) => {
        if (t.type === 'file' && isTabDirty(t)) void saveTab(t.id);
      });
    };
    window.addEventListener('blur', onBlur);
    return () => window.removeEventListener('blur', onBlur);
  }, [autoSave, saveTab]);

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <div className="flex h-10 shrink-0 items-stretch border-b border-white/[0.06]">
        <WorkbenchTabs onRequestClose={requestClose} />
        <button
          type="button"
          onClick={() => setRightPanelOpen(false)}
          className="grid w-10 shrink-0 place-items-center border-l border-white/[0.06] text-[#5c5855] transition-colors hover:bg-white/[0.06] hover:text-[#e8e6e3]"
          title="关闭工作台面板"
        >
          <PanelRightClose className="h-4 w-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {!activeTab && (
          <div className="flex h-full items-center justify-center text-[12px] text-[#5c5855]">没有打开的标签页</div>
        )}
        {activeTab?.type === 'state' && <StatePanel />}
        {activeTab?.type === 'file' && <FileRenderer tab={activeTab} />}
        {activeTab?.type === 'settings' && <SettingsTab />}
      </div>

      {pendingClose && (
        <ConfirmCloseDialog
          fileName={pendingClose.title}
          onCancel={() => setPendingClose(null)}
          onDiscard={() => { closeTab(pendingClose.id); setPendingClose(null); }}
          onSave={async () => {
            await saveTab(pendingClose.id);
            closeTab(pendingClose.id);
            setPendingClose(null);
          }}
        />
      )}
    </div>
  );
}
