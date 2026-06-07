import { create } from 'zustand';
import type { NewReference } from '@/stores/referenceStore';

interface InlinePromptState {
  open: boolean;
  draft: NewReference | null;
  position: { left: number; top: number } | null;
  openPrompt: (draft: NewReference, position: { left: number; top: number }) => void;
  close: () => void;
}

/** Controls the floating inline AI prompt that attaches an instruction to a selection. */
export const useInlinePromptStore = create<InlinePromptState>((set) => ({
  open: false,
  draft: null,
  position: null,
  openPrompt: (draft, position) => set({ open: true, draft, position }),
  close: () => set({ open: false, draft: null, position: null }),
}));
