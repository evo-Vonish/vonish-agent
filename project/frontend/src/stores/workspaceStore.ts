import { create } from 'zustand';
import type { FileNode, GitStatus, WorkspaceSummary } from '@/types';
import {
  getWorkspaceGitStatus,
  listWorkspaceFiles,
  listWorkspaces,
  openWorkspace,
  refreshWorkspace,
  type WorkspaceFileItem,
} from '@/services/api';

interface WorkspaceState {
  /** Current workspace conversation ID (null = no workspace loaded) */
  conversationId: string | null;
  workspaces: WorkspaceSummary[];
  activeWorkspaceId: string | null;
  gitStatus: GitStatus | null;
  /** File tree built from flat API response */
  fileTree: FileNode[];
  /** Whether the file list is loading */
  loading: boolean;
  /** Whether the workspace API responded (false = first load or empty) */
  loaded: boolean;

  /** Load the workspace for a conversation. Called when conversation switches. */
  loadWorkspace: (conversationId: string | null) => Promise<void>;
  loadWorkspaceList: () => Promise<void>;
  selectWorkspace: (workspaceId: string) => Promise<void>;
  refreshActiveWorkspace: () => Promise<void>;
  openActiveWorkspace: () => Promise<void>;
}

/**
 * Build a tree of FileNode from a flat list of backend file entries.
 */
function statusMap(git: GitStatus | null): Map<string, FileNode['gitStatus']> {
  const map = new Map<string, FileNode['gitStatus']>();
  git?.modified?.forEach((path) => map.set(path, 'modified'));
  git?.staged?.forEach((path) => map.set(path, 'modified'));
  git?.untracked?.forEach((path) => map.set(path, 'untracked'));
  git?.deleted?.forEach((path) => map.set(path, 'deleted'));
  git?.conflicts?.forEach((path) => map.set(path, 'conflict'));
  return map;
}

function buildFileTree(items: WorkspaceFileItem[], git: GitStatus | null = null): FileNode[] {
  const root: FileNode[] = [];
  const folderMap = new Map<string, FileNode>();
  const gitMap = statusMap(git);

  // Sort: directories first, then alphabetically
  const sorted = [...items].sort((a, b) => {
    if (a.type !== b.type) return a.type === 'folder' ? -1 : 1;
    const depthA = a.path.split('/').length;
    const depthB = b.path.split('/').length;
    if (depthA !== depthB) return depthA - depthB;
    return a.path.localeCompare(b.path);
  });

  for (const item of sorted) {
    const node: FileNode = {
      id: item.path,
      name: item.name,
      type: item.type,
      path: item.path,
      size: item.size,
      modifiedAt: item.modified_at ? Date.parse(item.modified_at) : undefined,
      gitStatus: (item.git_status as FileNode['gitStatus']) || gitMap.get(item.path) || 'clean',
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
  workspaces: [],
  activeWorkspaceId: null,
  gitStatus: null,
  fileTree: [],
  loading: false,
  loaded: false,

  loadWorkspace: async (conversationId) => {
    if (!conversationId) {
      set({ conversationId: null, activeWorkspaceId: null, gitStatus: null, fileTree: [], loaded: false });
      return;
    }

    set({ conversationId, activeWorkspaceId: conversationId, loading: true });

    try {
      const [files, git] = await Promise.all([
        listWorkspaceFiles(conversationId),
        getWorkspaceGitStatus(conversationId).catch(() => null),
      ]);
      const tree = buildFileTree(files, git);
      set({ fileTree: tree, gitStatus: git, loading: false, loaded: true });
    } catch {
      set({ fileTree: [], loading: false, loaded: false });
    }
  },

  loadWorkspaceList: async () => {
    try {
      const result = await listWorkspaces();
      set({ workspaces: result.workspaces });
    } catch {
      set({ workspaces: [] });
    }
  },

  selectWorkspace: async (workspaceId) => {
    set({ activeWorkspaceId: workspaceId, loading: true });
    try {
      const [files, git] = await Promise.all([
        listWorkspaceFiles(workspaceId),
        getWorkspaceGitStatus(workspaceId).catch(() => null),
      ]);
      set({ fileTree: buildFileTree(files, git), gitStatus: git, loading: false, loaded: true });
    } catch {
      set({ fileTree: [], gitStatus: null, loading: false, loaded: false });
    }
  },

  refreshActiveWorkspace: async () => {
    const workspaceId = useWorkspaceStore.getState().activeWorkspaceId;
    if (!workspaceId) return;
    set({ loading: true });
    try {
      const result = await refreshWorkspace(workspaceId);
      set({ fileTree: buildFileTree(result.files, result.git), gitStatus: result.git, loading: false, loaded: true });
    } catch {
      set({ loading: false });
    }
  },

  openActiveWorkspace: async () => {
    const workspaceId = useWorkspaceStore.getState().activeWorkspaceId;
    if (!workspaceId) return;
    await openWorkspace(workspaceId);
  },
}));
