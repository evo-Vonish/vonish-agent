import { create } from 'zustand';
import { useWorkbenchStore } from '@/stores/workbenchStore';

export interface ProposedEdit {
  tabId: string;
  summary: string;
  newContent: string;
  status: 'proposed';
}

interface ProposedEditState {
  edits: Record<string, ProposedEdit>;
  propose: (tabId: string, newContent: string, summary?: string) => void;
  apply: (tabId: string) => void;
  reject: (tabId: string) => void;
}

/**
 * Holds AI-proposed edits per tab. Edits are never applied silently — the user
 * must Apply (updates the editor buffer → dirty → save with Ctrl+S) or Reject.
 *
 * Integration seam: the chat/agent layer (or `window.__vonish_proposeEdit`)
 * calls `propose(tabId, newContent, summary)` when the agent returns an edit.
 */
export const useProposedEditStore = create<ProposedEditState>((set, get) => ({
  edits: {},
  propose: (tabId, newContent, summary = 'AI 提议的修改') =>
    set((state) => ({ edits: { ...state.edits, [tabId]: { tabId, newContent, summary, status: 'proposed' } } })),
  apply: (tabId) => {
    const edit = get().edits[tabId];
    if (edit) useWorkbenchStore.getState().updateContent(tabId, edit.newContent);
    set((state) => {
      const next = { ...state.edits };
      delete next[tabId];
      return { edits: next };
    });
  },
  reject: (tabId) =>
    set((state) => {
      const next = { ...state.edits };
      delete next[tabId];
      return { edits: next };
    }),
}));

// Integration/test hook so the agent layer can propose edits into the workbench.
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).__vonish_proposeEdit = (
    tabId: string,
    newContent: string,
    summary?: string,
  ) => useProposedEditStore.getState().propose(tabId, newContent, summary);
}
