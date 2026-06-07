import { create } from 'zustand';
import type { Reference, ReferenceLocation, ReferenceSourceType } from '@/types';
import { generateId } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { useWorkbenchStore } from '@/stores/workbenchStore';

export interface NewReference {
  sourceType: ReferenceSourceType;
  sourceId?: string;
  title: string;
  preview: string;
  instruction?: string;
  location?: ReferenceLocation;
  payload?: unknown;
}

interface ReferenceState {
  references: Reference[];
  addReference: (input: NewReference) => Reference;
  removeReference: (id: string) => void;
  clearReferences: () => void;
  attachInstruction: (id: string, instruction: string) => void;
  /** Jump back to the original source of a reference (open tab + reveal, or scroll chat). */
  focusSource: (id: string) => void;
}

/** Temporarily highlight a chat message element (jump-back for chat quotes). */
function flashElement(selector: string) {
  if (typeof document === 'undefined') return;
  const el = document.querySelector(selector);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.add('ref-flash');
  window.setTimeout(() => el.classList.remove('ref-flash'), 1600);
}

export const useReferenceStore = create<ReferenceState>((set, get) => ({
  references: [],

  addReference: (input) => {
    const ref: Reference = {
      id: generateId(),
      sourceType: input.sourceType,
      sourceId: input.sourceId ?? generateId(),
      title: input.title,
      preview: input.preview,
      instruction: input.instruction,
      location: input.location,
      payload: input.payload,
      createdAt: Date.now(),
    };
    set((state) => ({ references: [...state.references, ref] }));
    return ref;
  },

  removeReference: (id) => set((state) => ({ references: state.references.filter((r) => r.id !== id) })),

  clearReferences: () => set({ references: [] }),

  attachInstruction: (id, instruction) =>
    set((state) => ({ references: state.references.map((r) => (r.id === id ? { ...r, instruction } : r)) })),

  focusSource: (id) => {
    const ref = get().references.find((r) => r.id === id);
    if (!ref) return;
    const loc = ref.location;

    if (ref.sourceType === 'chat') {
      const messageId = loc?.messageId ?? ref.sourceId;
      flashElement(`[data-msg-id="${messageId}"]`);
      return;
    }

    if (loc?.filePath) {
      useUIStore.getState().setRightPanelOpen(true);
      void useWorkbenchStore.getState().openFile(loc.workspaceId ?? null, loc.filePath, {
        reveal: {
          lineStart: loc.lineStart,
          lineEnd: loc.lineEnd,
          blockId: loc.blockId,
          elementId: loc.elementId,
          cssPath: loc.cssPath,
          pageIndex: loc.pageIndex,
          sheetName: loc.sheetName,
          cellRange: loc.cellRange,
          slideIndex: loc.slideIndex,
        },
      });
    }
  },
}));

// Integration/automation surface: lets the agent layer (or external tooling)
// add/inspect references programmatically — also used for headless verification.
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).__vonishRefs = {
    add: (r: NewReference) => useReferenceStore.getState().addReference(r),
    list: () => useReferenceStore.getState().references,
    clear: () => useReferenceStore.getState().clearReferences(),
    focus: (id: string) => useReferenceStore.getState().focusSource(id),
  };
}
