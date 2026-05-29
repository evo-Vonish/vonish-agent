import { create } from 'zustand';
import type { FileNode } from '@/types';
import { listWorkspaceFiles, type WorkspaceFileItem } from '@/services/api';

interface WorkspaceState {
  /** Current workspace conversation ID (null = no workspace loaded) */
  conversationId: string | null;
  /** File tree built from flat API response */
  fileTree: FileNode[];
  /** Whether the file list is loading */
  loading: boolean;
  /** Whether the workspace API responded (false = first load or empty) */
  loaded: boolean;

  /** Load the workspace for a conversation. Called when conversation switches. */
  loadWorkspace: (conversationId: string | null) => Promise<void>;
}

/**
 * Build a tree of FileNode from a flat list of backend file entries.
 */
function buildFileTree(items: WorkspaceFileItem[]): FileNode[] {
  const root: FileNode[] = [];
  const folderMap = new Map<string, FileNode>();

  // Sort: directories first, then alphabetically
  const sorted = [...items].sort((a, b) => {
    if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
    return a.name.localeCompare(b.name);
  });

  for (const item of sorted) {
    const node: FileNode = {
      id: item.path,
      name: item.name,
      type: item.type,
      path: item.path,
      size: item.size,
      modifiedAt: item.modified_at ? Date.parse(item.modified_at) : undefined,
      children: item.type === 'folder' ? [] : undefined,
    };

    const parentPath = item.path.substring(0, item.path.lastIndexOf('/'));
    if (!parentPath || parentPath === '') {
      root.push(node);
    } else {
      const parent = folderMap.get(parentPath);
      if (parent?.children) {
        parent.children.push(node);
      } else {
        // Orphan: put at root
        root.push(node);
      }
    }

    if (item.type === 'folder') {
      folderMap.set(item.path, node);
    }
  }

  return root;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  conversationId: null,
  fileTree: [],
  loading: false,
  loaded: false,

  loadWorkspace: async (conversationId) => {
    if (!conversationId) {
      set({ conversationId: null, fileTree: [], loaded: false });
      return;
    }

    set({ conversationId, loading: true });

    try {
      const files = await listWorkspaceFiles(conversationId);
      const tree = buildFileTree(files);
      set({ fileTree: tree, loading: false, loaded: true });
    } catch {
      set({ fileTree: [], loading: false, loaded: false });
    }
  },
}));
