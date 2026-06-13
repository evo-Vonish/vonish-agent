import { create } from 'zustand';
import { baseName, detectFileType, type FileKind } from '@/lib/fileTypes';
import { previewWorkspaceFile, readWorkspaceFile, saveWorkspaceFile } from '@/services/api';
import { useUIStore } from '@/stores/uiStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';

export type WorkbenchTabType = 'file' | 'settings' | 'state' | 'browser';

export interface WorkbenchTab {
  id: string;
  type: WorkbenchTabType;
  title: string;
  workspaceId?: string | null;
  path?: string;
  ext?: string;
  kind?: FileKind;
  language?: string;
  mimeType?: string;
  size?: number;
  encoding?: 'utf-8' | 'base64';
  /** Current (possibly edited) text content, or base64 for images. */
  content?: string;
  /** Last persisted text content — used to compute the dirty flag. */
  savedContent?: string;
  editable?: boolean;
  readonly?: boolean;
  loading?: boolean;
  error?: string | null;
  truncated?: boolean;
}

export interface RevealTarget {
  lineStart?: number;
  lineEnd?: number;
  blockId?: string;
  elementId?: string;
  cssPath?: string;
  pageIndex?: number;
  sheetName?: string;
  cellRange?: string;
  slideIndex?: number;
}

export interface RevealRequest extends RevealTarget {
  tabId: string;
  /** Bumped on each request so renderers re-run even for the same target. */
  token: number;
}

const STATE_TAB: WorkbenchTab = { id: 'state', type: 'state', title: 'State' };

function clampWidth(width: number): number {
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1440;
  const max = Math.min(1100, Math.round(vw * 0.75));
  return Math.max(360, Math.min(max, Math.round(width)));
}

function editorWidthFloor(current: number): number {
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1440;
  return clampWidth(Math.max(current, Math.min(760, Math.round(vw * 0.5))));
}

let revealToken = 1;

interface WorkbenchState {
  tabs: WorkbenchTab[];
  activeTabId: string | null;
  panelWidth: number;
  reveal: RevealRequest | null;
  /** Per-(workspace:path) counter bumped when an artifact is regenerated, so
   *  an already-open renderer (e.g. a deck after agent patch/revert) re-fetches. */
  artifactRefresh: Record<string, number>;

  setPanelWidth: (width: number | ((prev: number) => number)) => void;
  setActiveTab: (id: string) => void;
  openSpecialTab: (type: 'settings' | 'state') => void;
  signalArtifactRefresh: (workspaceId: string | null | undefined, path: string) => void;
  openFile: (
    workspaceId: string | null,
    path: string,
    opts?: { reveal?: RevealTarget },
  ) => Promise<void>;
  closeTab: (id: string) => void;
  updateContent: (id: string, content: string) => void;
  saveTab: (id: string) => Promise<void>;
  requestReveal: (tabId: string, target?: RevealTarget) => void;
}

export const useWorkbenchStore = create<WorkbenchState>((set, get) => ({
  tabs: [STATE_TAB],
  activeTabId: 'state',
  panelWidth: 460,
  reveal: null,
  artifactRefresh: {},

  signalArtifactRefresh: (workspaceId, path) => {
    const key = `${workspaceId ?? ''}:${path}`;
    set((state) => ({ artifactRefresh: { ...state.artifactRefresh, [key]: (state.artifactRefresh[key] ?? 0) + 1 } }));
  },

  setPanelWidth: (width) =>
    set((state) => ({
      panelWidth: clampWidth(typeof width === 'function' ? width(state.panelWidth) : width),
    })),

  setActiveTab: (id) => {
    if (get().tabs.some((tab) => tab.id === id)) set({ activeTabId: id });
  },

  openSpecialTab: (type) => {
    useUIStore.getState().setRightPanelOpen(true);
    set((state) => {
      if (state.tabs.some((tab) => tab.id === type)) return { activeTabId: type };
      const tab: WorkbenchTab = { id: type, type, title: type === 'settings' ? 'Settings' : 'State' };
      return { tabs: [...state.tabs, tab], activeTabId: type };
    });
  },

  openFile: async (workspaceId, path, opts) => {
    const id = `file:${workspaceId ?? ''}:${path}`;
    useUIStore.getState().setRightPanelOpen(true);

    const existing = get().tabs.find((tab) => tab.id === id);
    if (existing) {
      set({ activeTabId: id });
      if (opts?.reveal) get().requestReveal(id, opts.reveal);
      return;
    }

    const info = detectFileType(path);
    const tab: WorkbenchTab = {
      id,
      type: 'file',
      title: baseName(path),
      workspaceId,
      path,
      ext: info.ext,
      kind: info.kind,
      language: info.language,
      mimeType: info.mime,
      editable: info.editable,
      readonly: !info.editable,
      loading: true,
      error: null,
    };
    set((state) => ({
      tabs: [...state.tabs, tab],
      activeTabId: id,
      panelWidth: editorWidthFloor(state.panelWidth),
    }));

    const patch = (changes: Partial<WorkbenchTab>) =>
      set((state) => ({ tabs: state.tabs.map((t) => (t.id === id ? { ...t, ...changes } : t)) }));

    if (!workspaceId) {
      patch({ loading: false, error: '未选择 Workspace，无法打开文件。' });
      return;
    }

    try {
      if (info.editable) {
        const res = await readWorkspaceFile(workspaceId, path);
        if (res.encoding === 'base64') {
          // Extension looked like text, but the bytes are not UTF-8 — treat as binary.
          patch({ loading: false, kind: 'binary', editable: false, readonly: true });
        } else {
          patch({ loading: false, content: res.content, savedContent: res.content, encoding: 'utf-8' });
        }
      } else if (info.kind === 'image') {
        const preview = await previewWorkspaceFile(workspaceId, path);
        patch({
          loading: false,
          content: preview.content || '',
          encoding: 'base64',
          mimeType: preview.mime_type ?? info.mime,
          size: preview.size,
          truncated: !preview.content,
          readonly: true,
        });
      } else {
        const preview = await previewWorkspaceFile(workspaceId, path).catch(() => null);
        patch({ loading: false, size: preview?.size, mimeType: preview?.mime_type ?? info.mime, readonly: true });
      }
    } catch (err) {
      patch({ loading: false, error: err instanceof Error ? err.message : '无法打开文件。' });
    }

    if (opts?.reveal) get().requestReveal(id, opts.reveal);
  },

  closeTab: (id) => {
    set((state) => {
      const index = state.tabs.findIndex((tab) => tab.id === id);
      if (index === -1) return state;
      const tabs = state.tabs.filter((tab) => tab.id !== id);
      let activeTabId = state.activeTabId;
      if (activeTabId === id) {
        const next = tabs[index] ?? tabs[index - 1] ?? tabs[tabs.length - 1] ?? null;
        activeTabId = next ? next.id : null;
      }
      return { tabs, activeTabId };
    });
  },

  updateContent: (id, content) => {
    set((state) => ({ tabs: state.tabs.map((tab) => (tab.id === id ? { ...tab, content } : tab)) }));
  },

  saveTab: async (id) => {
    const tab = get().tabs.find((item) => item.id === id);
    if (!tab || tab.type !== 'file' || tab.readonly || tab.content === undefined) return;
    await saveWorkspaceFile(tab.workspaceId ?? '', tab.path ?? '', tab.content);
    set((state) => ({
      tabs: state.tabs.map((item) => (item.id === id ? { ...item, savedContent: item.content } : item)),
    }));
    // Refresh the explorer/git so the saved change is reflected.
    void useWorkspaceStore.getState().refreshActiveWorkspace();
  },

  requestReveal: (tabId, target) => {
    revealToken += 1;
    set({ reveal: { tabId, token: revealToken, ...(target ?? {}) } });
  },
}));

/** A file tab is dirty when its editable content differs from what was saved. */
export function isTabDirty(tab: WorkbenchTab): boolean {
  return tab.type === 'file' && !tab.readonly && tab.content !== undefined && tab.content !== tab.savedContent;
}
