import { create } from 'zustand';
import type { NewReference } from '@/stores/referenceStore';

export interface RectLike {
  left: number;
  top: number;
  bottom: number;
  right: number;
}

export interface QuotableSelection {
  draft: NewReference;
  rect: RectLike | null;
  /** Origin tag so a source only clears its own selection (e.g. 'dom' or a file path). */
  origin: string;
}

interface SelectionState {
  current: QuotableSelection | null;
  setSelection: (sel: QuotableSelection | null) => void;
  clearOrigin: (origin: string) => void;
}

/** Holds the current quotable selection (text in chat/markdown, or a CodeMirror range). */
export const useSelectionStore = create<SelectionState>((set, get) => ({
  current: null,
  setSelection: (sel) => set({ current: sel }),
  clearOrigin: (origin) => {
    if (get().current?.origin === origin) set({ current: null });
  },
}));
