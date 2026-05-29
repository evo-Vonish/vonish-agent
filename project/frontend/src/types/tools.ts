export type ToolCategoryType = 'file_ops' | 'web_search' | 'workspace' | 'system';

export type ToolCapability = 'read_only' | 'writes_files' | 'requires_approval';

export type ApprovalLevel = 'auto' | 'suggest' | 'required';

export interface ToolDefinition {
  name: string;
  description: string;
  category: ToolCategoryType;
  capabilities: ToolCapability[];
  approvalLevel: ApprovalLevel;
  isEnabled: boolean;
  isReadOnly: boolean;
  supportsParallel: boolean;
  schema: Record<string, unknown>;
  lastUsed?: string;
  useCount: number;
}

export interface ToolCategory {
  id: ToolCategoryType;
  label: string;
  icon: string;
  tools: ToolDefinition[];
}

export const APPROVAL_LEVEL_COLORS: Record<ApprovalLevel, string> = {
  auto: 'bg-success/20 text-success border-success/30',
  suggest: 'bg-warning/20 text-warning border-warning/30',
  required: 'bg-error/20 text-error border-error/30',
};

export const APPROVAL_LEVEL_LABELS: Record<ApprovalLevel, string> = {
  auto: 'Auto',
  suggest: 'Suggest',
  required: 'Required',
};

export const CATEGORY_ICONS: Record<ToolCategoryType, string> = {
  file_ops: 'FolderOpen',
  workspace: 'Layout',
  web_search: 'Globe',
  system: 'Terminal',
};

export const CATEGORY_LABELS: Record<ToolCategoryType, string> = {
  file_ops: 'File Operations',
  workspace: 'Workspace',
  web_search: 'Web Search',
  system: 'System',
};
