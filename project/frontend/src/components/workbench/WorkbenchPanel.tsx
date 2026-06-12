import { useEffect, useState } from 'react';
import { History, PanelRightClose, RotateCcw } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { isTabDirty, useWorkbenchStore, type WorkbenchTab } from '@/stores/workbenchStore';
import { useSettingsStore } from '@/stores/settingsStore';
import { getArtifactVersions, restoreArtifactVersion, type ArtifactVersionItem } from '@/services/api';
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
  const openFile = useWorkbenchStore((s) => s.openFile);
  const setRightPanelOpen = useUIStore((s) => s.setRightPanelOpen);
  const autoSave = useSettingsStore((s) => s.autoSave);
  const [pendingClose, setPendingClose] = useState<WorkbenchTab | null>(null);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState('');
  const [versions, setVersions] = useState<ArtifactVersionItem[]>([]);

  const activeTab = tabs.find((t) => t.id === activeTabId) ?? null;

  const requestClose = (tab: WorkbenchTab) => {
    if (isTabDirty(tab)) setPendingClose(tab);
    else closeTab(tab.id);
  };

  const loadVersions = async () => {
    if (!activeTab || activeTab.type !== 'file' || !activeTab.workspaceId || !activeTab.path) return;
    setVersionsOpen((value) => !value);
    setVersionsError('');
    setVersionsLoading(true);
    try {
      const result = await getArtifactVersions(activeTab.workspaceId, activeTab.path);
      setVersions(result.versions);
    } catch (error) {
      setVersionsError(error instanceof Error ? error.message : String(error));
    } finally {
      setVersionsLoading(false);
    }
  };

  const restoreVersion = async (version: number) => {
    if (!activeTab || activeTab.type !== 'file' || !activeTab.workspaceId || !activeTab.path) return;
    setVersionsError('');
    try {
      const result = await restoreArtifactVersion(activeTab.workspaceId, activeTab.path, version);
      if (!result.success) throw new Error(result.error || 'Restore failed');
      const { id, workspaceId, path } = activeTab;
      closeTab(id);
      await openFile(workspaceId ?? null, path);
      setVersionsOpen(false);
    } catch (error) {
      setVersionsError(error instanceof Error ? error.message : String(error));
    }
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

  useEffect(() => {
    setVersionsOpen(false);
    setVersions([]);
    setVersionsError('');
  }, [activeTabId]);

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <div className="flex h-10 shrink-0 items-stretch border-b border-white/[0.06]">
        <WorkbenchTabs onRequestClose={requestClose} />
        {activeTab?.type === 'file' && (
          <div className="relative border-l border-white/[0.06]">
            <button
              type="button"
              onClick={() => void loadVersions()}
              className="grid h-10 w-10 place-items-center text-[#5c5855] transition-colors hover:bg-white/[0.06] hover:text-[#e8e6e3]"
              title="版本"
            >
              <History className="h-4 w-4" />
            </button>
            {versionsOpen && (
              <div className="absolute right-0 top-10 z-30 w-72 rounded-xl border border-white/10 bg-[#202020] p-2 text-xs text-[#d8d4cf] shadow-2xl">
                <div className="px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-[#8e8984]">Artifact Versions</div>
                {versionsLoading && <div className="px-2 py-3 text-[#8e8984]">Loading...</div>}
                {!versionsLoading && versionsError && <div className="px-2 py-3 text-error">{versionsError}</div>}
                {!versionsLoading && !versionsError && versions.length === 0 && (
                  <div className="px-2 py-3 text-[#8e8984]">No versions yet</div>
                )}
                {!versionsLoading && !versionsError && versions.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => void restoreVersion(item.version)}
                    className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left hover:bg-white/[0.06]"
                  >
                    <RotateCcw className="h-3.5 w-3.5 text-[#9a9590]" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">V{item.version} · {item.label || item.commit_hash.slice(0, 10)}</span>
                      <span className="block truncate text-[10px] text-[#8e8984]">{item.created_at}</span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
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
