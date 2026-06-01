import { create } from 'zustand';
import type { PermissionDraftMode, DirectoryAccessDraftMode } from '@/types';

interface SessionDraftState {
  workspaceId: string | null;
  permissionMode: PermissionDraftMode;
  directoryAccessMode: DirectoryAccessDraftMode;
  setWorkspaceId: (id: string | null) => void;
  setPermissionMode: (mode: PermissionDraftMode) => void;
  setDirectoryAccessMode: (mode: DirectoryAccessDraftMode) => void;
  reset: () => void;
}

const defaults = {
  workspaceId: null as string | null,
  permissionMode: 'default' as PermissionDraftMode,
  directoryAccessMode: 'locked_workspace' as DirectoryAccessDraftMode,
};

export const useSessionDraftStore = create<SessionDraftState>((set) => ({
  ...defaults,
  setWorkspaceId: (id) => set({ workspaceId: id }),
  setPermissionMode: (mode) => set({ permissionMode: mode }),
  setDirectoryAccessMode: (mode) => set({ directoryAccessMode: mode }),
  reset: () => set(defaults),
}));
