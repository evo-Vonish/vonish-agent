import { create } from 'zustand';
import type { ToolDefinition, ToolCategoryType, ToolCapability, ApprovalLevel } from '@/types/tools';
import { fetchToolConfigs, enableTool, disableTool, listTools } from '@/services/api';

interface ToolState {
  tools: ToolDefinition[];
  toggleTool: (name: string) => void;
  syncFromBackend: () => Promise<void>;
  loadToolsFromBackend: () => Promise<void>;
  enableCategory: (category: ToolCategoryType) => void;
  disableCategory: (category: ToolCategoryType) => void;
  getEnabledTools: () => ToolDefinition[];
  getToolByName: (name: string) => ToolDefinition | undefined;
  updateToolUsage: (name: string) => void;
  addTool: (tool: ToolDefinition) => void;
  getToolsByCategory: (category: ToolCategoryType) => ToolDefinition[];
  getCategories: () => ToolCategoryType[];
}

const mockTools: ToolDefinition[] = [
  // File Operations
  {
    name: 'write_to_file',
    description: 'Create or overwrite files in the workspace',
    category: 'file_ops',
    capabilities: ['writes_files'],
    approvalLevel: 'suggest',
    isEnabled: true,
    isReadOnly: false,
    supportsParallel: false,
    schema: {
      type: 'object',
      properties: {
        file_path: { type: 'string', description: 'Path to the file to write' },
        content: { type: 'string', description: 'Content to write to the file' },
      },
      required: ['file_path', 'content'],
    },
    lastUsed: '2025-05-28T09:15:00Z',
    useCount: 342,
  },
  {
    name: 'edit_file',
    description: 'Edit files with search/replace operations',
    category: 'file_ops',
    capabilities: ['writes_files'],
    approvalLevel: 'suggest',
    isEnabled: true,
    isReadOnly: false,
    supportsParallel: false,
    schema: {
      type: 'object',
      properties: {
        file_path: { type: 'string', description: 'Path to the file to edit' },
        old_string: { type: 'string', description: 'String to search for' },
        new_string: { type: 'string', description: 'Replacement string' },
      },
      required: ['file_path', 'old_string', 'new_string'],
    },
    lastUsed: '2025-05-27T16:45:00Z',
    useCount: 567,
  },
  {
    name: 'apply_patch',
    description: 'Apply unified diff patches to files',
    category: 'file_ops',
    capabilities: ['writes_files'],
    approvalLevel: 'suggest',
    isEnabled: false,
    isReadOnly: false,
    supportsParallel: false,
    schema: {
      type: 'object',
      properties: {
        file_path: { type: 'string', description: 'Path to the file to patch' },
        patch: { type: 'string', description: 'Unified diff patch to apply' },
      },
      required: ['file_path', 'patch'],
    },
    lastUsed: undefined,
    useCount: 0,
  },
  {
    name: 'delete_file',
    description: 'Delete workspace files',
    category: 'file_ops',
    capabilities: ['writes_files', 'requires_approval'],
    approvalLevel: 'required',
    isEnabled: true,
    isReadOnly: false,
    supportsParallel: false,
    schema: {
      type: 'object',
      properties: {
        file_path: { type: 'string', description: 'Path to the file to delete' },
        confirm: { type: 'boolean', description: 'Confirm deletion' },
      },
      required: ['file_path', 'confirm'],
    },
    lastUsed: '2025-05-20T08:00:00Z',
    useCount: 23,
  },
  // Workspace
  {
    name: 'list_workspace_files',
    description: 'List all files in the workspace',
    category: 'workspace',
    capabilities: ['read_only'],
    approvalLevel: 'auto',
    isEnabled: true,
    isReadOnly: true,
    supportsParallel: true,
    schema: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'Directory path to list' },
        recursive: { type: 'boolean', description: 'List recursively' },
      },
      required: ['path'],
    },
    lastUsed: '2025-05-28T11:00:00Z',
    useCount: 892,
  },
  {
    name: 'read_workspace_file',
    description: 'Read a file from the workspace with metadata',
    category: 'workspace',
    capabilities: ['read_only'],
    approvalLevel: 'auto',
    isEnabled: true,
    isReadOnly: true,
    supportsParallel: true,
    schema: {
      type: 'object',
      properties: {
        file_path: { type: 'string', description: 'Path to the file' },
        encoding: { type: 'string', description: 'File encoding', enum: ['utf-8', 'base64'] },
      },
      required: ['file_path'],
    },
    lastUsed: '2025-05-28T10:45:00Z',
    useCount: 756,
  },
  {
    name: 'create_workspace_snapshot',
    description: 'Create a snapshot of the current workspace state',
    category: 'workspace',
    capabilities: ['writes_files'],
    approvalLevel: 'suggest',
    isEnabled: true,
    isReadOnly: false,
    supportsParallel: false,
    schema: {
      type: 'object',
      properties: {
        name: { type: 'string', description: 'Snapshot name' },
        include_files: { type: 'array', items: { type: 'string' }, description: 'Files to include' },
      },
      required: ['name'],
    },
    lastUsed: '2025-05-25T14:20:00Z',
    useCount: 45,
  },
  // Web Search
  {
    name: 'web_search',
    description: 'Search the web for information',
    category: 'web_search',
    capabilities: ['read_only'],
    approvalLevel: 'auto',
    isEnabled: true,
    isReadOnly: true,
    supportsParallel: true,
    schema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search query' },
        num_results: { type: 'number', description: 'Number of results to return' },
        max_time_ms: { type: 'number', description: 'Overall search and crawl budget in ms' },
        max_content_length: { type: 'number', description: 'Maximum returned text length' },
        per_url_timeout_ms: { type: 'number', description: 'Per-page crawl timeout in ms' },
        max_per_url: { type: 'number', description: 'Maximum extracted text per page' },
      },
      required: ['query'],
    },
    lastUsed: undefined,
    useCount: 0,
  },
  {
    name: 'web_fetch',
    description: 'Fetch content from a specific URL',
    category: 'web_search',
    capabilities: ['read_only', 'requires_approval'],
    approvalLevel: 'auto',
    isEnabled: false,
    isReadOnly: true,
    supportsParallel: true,
    schema: {
      type: 'object',
      properties: {
        url: { type: 'string', description: 'URL to fetch' },
        method: { type: 'string', enum: ['GET', 'POST'], description: 'HTTP method' },
      },
      required: ['url'],
    },
    lastUsed: undefined,
    useCount: 0,
  },
  // System
  {
    name: 'exec_shell',
    description: 'Execute shell commands',
    category: 'system',
    capabilities: ['writes_files', 'requires_approval'],
    approvalLevel: 'required',
    isEnabled: false,
    isReadOnly: false,
    supportsParallel: false,
    schema: {
      type: 'object',
      properties: {
        command: { type: 'string', description: 'Shell command to execute' },
        timeout: { type: 'number', description: 'Timeout in seconds' },
        cwd: { type: 'string', description: 'Working directory' },
      },
      required: ['command'],
    },
    lastUsed: undefined,
    useCount: 0,
  },
  {
    name: 'ipython',
    description: 'Execute Python code in a persistent IPython kernel',
    category: 'python_ops',
    capabilities: ['writes_files', 'requires_approval'],
    approvalLevel: 'required',
    isEnabled: true,
    isReadOnly: false,
    supportsParallel: false,
    schema: {
      type: 'object',
      properties: {
        code: { type: 'string', description: 'Python code to execute' },
        session_mode: { type: 'string', enum: ['continue', 'new', 'reset', 'ephemeral'], description: 'Kernel session mode' },
        session_id: { type: 'string', description: 'Optional named session id' },
        timeout_seconds: { type: 'number', description: 'Execution timeout in seconds' },
        restart: { type: 'boolean', description: 'Restart the IPython environment' },
      },
      required: ['code'],
    },
    lastUsed: undefined,
    useCount: 0,
  },
];

export const useToolStore = create<ToolState>((set, get) => ({
  tools: mockTools,

  toggleTool: async (name) => {
    const current = get().tools.find((t) => t.name === name);
    if (!current) return;
    const newState = !current.isEnabled;
    // Optimistic UI update
    set((state) => ({
      tools: state.tools.map((t) =>
        t.name === name ? { ...t, isEnabled: newState } : t
      ),
    }));
    // Sync to backend
    try {
      if (newState) await enableTool(name);
      else await disableTool(name);
    } catch {
      // Revert on failure
      set((state) => ({
        tools: state.tools.map((t) =>
          t.name === name ? { ...t, isEnabled: !newState } : t
        ),
      }));
    }
  },

  loadToolsFromBackend: async () => {
    try {
      const { tools: backendTools } = await listTools();
      const mapped: ToolDefinition[] = backendTools.map((t) => ({
        name: t.name,
        description: t.description,
        category: t.category as ToolCategoryType,
        capabilities: (t.requires_confirmation || t.requires_approval
          ? ['requires_approval']
          : ['read_only']) as ToolCapability[],
        approvalLevel: ((t.requires_confirmation || t.requires_approval)
          ? 'required'
          : t.category === 'file_ops'
            ? 'suggest'
            : 'auto') as ApprovalLevel,
        isEnabled: t.enabled ?? true,
        isReadOnly: !t.requires_confirmation,
        supportsParallel: true,
        schema: t.schema,
        useCount: 0,
      }));
      set({ tools: mapped });
      // Sync enabled states from backend config
      await get().syncFromBackend();
    } catch {
      // Keep current state if backend unavailable
    }
  },

  syncFromBackend: async () => {
    try {
      const { tools: configs } = await fetchToolConfigs();
      set((state) => ({
        tools: state.tools.map((t) => ({
          ...t,
          isEnabled: configs[t.name] ?? t.isEnabled,
        })),
      }));
    } catch {
      // Keep current state if backend unavailable
    }
  },

  enableCategory: (category) =>
    set((state) => ({
      tools: state.tools.map((t) =>
        t.category === category ? { ...t, isEnabled: true } : t
      ),
    })),

  disableCategory: (category) =>
    set((state) => ({
      tools: state.tools.map((t) =>
        t.category === category ? { ...t, isEnabled: false } : t
      ),
    })),

  getEnabledTools: () => get().tools.filter((t) => t.isEnabled),

  getToolByName: (name) => get().tools.find((t) => t.name === name),

  updateToolUsage: (name) =>
    set((state) => ({
      tools: state.tools.map((t) =>
        t.name === name
          ? { ...t, useCount: t.useCount + 1, lastUsed: new Date().toISOString() }
          : t
      ),
    })),

  addTool: (tool) =>
    set((state) => ({
      tools: [...state.tools, tool],
    })),

  getToolsByCategory: (category) =>
    get().tools.filter((t) => t.category === category),

  getCategories: () => {
    const cats = new Set<ToolCategoryType>();
    get().tools.forEach((t) => cats.add(t.category));
    return Array.from(cats);
  },
}));
