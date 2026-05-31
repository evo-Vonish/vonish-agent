export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  type?: 'text' | 'thinking' | 'tool_call' | 'tool_result' | 'error' | 'interaction';
  interaction?: {
    interaction_id: string;
    type: 'ask_user_question' | 'request_approval';
    title: string;
    description?: string;
    options: { id: string; label: string; description?: string }[];
    allow_custom_response?: boolean;
    risk_level?: 'low' | 'medium' | 'high';
    plan?: { id: string; title: string; description?: string; risk?: string }[];
    resolved?: boolean;
    response?: { choice: string; message?: string };
  };
  todo?: { items: { id: string; title: string; status: string; note?: string }[]; count: number };
  thinkingContent?: string;
  thinkingBlocks?: string[];  // per-round thinking blocks (each round = one card)
  segments?: MessageSegment[];
  toolCalls?: ToolCall[];
  files?: UploadedFileMeta[];
  timestamp: number;
  status?: 'sending' | 'streaming' | 'complete' | 'error';
}

export interface UploadedFileMeta {
  id: string;
  originalName: string;
  safeName?: string;
  mimeType: string;
  ext: string;
  size: number;
  workspacePath: string;
  createdAt?: string;
  status: 'queued' | 'uploading' | 'uploaded' | 'parsed' | 'failed';
  textExtracted?: boolean;
  textLength?: number;
  textPreview?: string;
  contextPolicy?: 'none' | 'weak' | 'normal' | 'compressed';
  contextText?: string;
  resourceUri?: string;
  error?: string;
}

export type MessageSegment =
  | {
      id: string;
      type: 'thinking';
      content: string;
      summary?: string;
      status: 'streaming' | 'complete';
    }
  | {
      id: string;
      type: 'text';
      content: string;
    }
  | {
      id: string;
      type: 'tool';
      tool: ToolCall;
    }
  | {
      id: string;
      type: 'execution';
      execution: ExecutionSegment;
    }
  | {
      id: string;
      type: 'workflow_error';
      error: WorkflowError;
      retryPrompt?: string;
    };

export interface WorkflowErrorAction {
  id: string;
  label: string;
  style?: 'primary' | 'secondary' | 'danger';
}

export interface WorkflowError {
  id: string;
  segmentId?: string;
  stepId?: string;
  severity: 'info' | 'warning' | 'error' | 'fatal';
  errorType: string;
  title: string;
  message: string;
  recoverable: boolean;
  actions: WorkflowErrorAction[];
  detailsRef?: string;
}

export interface ExecutionStep {
  id: string;
  segmentId: string;
  type:
    | 'thinking'
    | 'tool_call'
    | 'tool_result'
    | 'file_read'
    | 'file_write'
    | 'file_edit'
    | 'command'
    | 'web_search'
    | 'web_fetch'
    | 'recall'
    | 'user_interaction'
    | 'system_notice'
    | 'error_notice';
  status: 'running' | 'completed' | 'failed' | 'cancelled' | 'skipped' | 'retrying';
  title: string;
  subtitle?: string;
  startedAt?: string;
  endedAt?: string;
  durationMs?: number;
  toolName?: string;
  toolCallId?: string;
  inputPreview?: string;
  outputPreview?: string;
  content?: string;
  error?: string;
  metadata?: Record<string, unknown>;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  raw?: unknown;
}

export interface ExecutionSegment {
  id: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled' | 'waiting_user';
  title?: string;
  goal?: string;
  startedAt?: string;
  endedAt?: string;
  durationMs?: number;
  thinkingCount: number;
  toolCallCount: number;
  commandCount: number;
  fileReadCount: number;
  fileWriteCount: number;
  fileEditCount: number;
  webRequestCount: number;
  recallCount: number;
  errorCount: number;
  totalTokens?: number;
  steps: ExecutionStep[];
  errors?: WorkflowError[];
  summary?: string;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  error?: string;
  status: 'pending' | 'running' | 'success' | 'error';
  duration?: number;
  startTime?: number;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  model: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
}

export interface Model {
  id: string;
  name: string;
  provider: string;
  description: string;
  maxTokens: number;
  contextWindow: number;
  tags?: string[];
}

export interface ContextProfile {
  id: string;
  name: string;
  tokenBudget: number;
  tokenUsed: number;
  messageRounds: number;
  memoryCount: number;
  fileCount: number;
  toolCount: number;
  compressionLevel: 'none' | 'light' | 'medium' | 'aggressive';
}

export interface ContextUsage {
  conversationId: string;
  totalTokens: number;
  maxTokens: number;
  availableBudget: number;
  outputReserved: number;
  safetyMargin: number;
  profile: string;
  model: string;
  usageRatio: number;
  compressionLevel: string;
  budgetHealthy: boolean;
  components: Record<string, number>;
  messageCount: number;
  userMessageCount: number;
  toolCallCount: number;
  workspaceFileCount: number;
  memoryItemCount: number;
}

export interface FileNode {
  id: string;
  name: string;
  type: 'file' | 'folder';
  path: string;
  children?: FileNode[];
  size?: number;
  modifiedAt?: number;
}

export interface Attachment {
  id: string;
  name: string;
  type: string;
  size: number;
  content?: string;
  uploading?: boolean;
  progress?: number;
}

export type FileChangeType = 'added' | 'modified' | 'deleted';

export interface FileChange {
  id: string;
  path: string;
  type: FileChangeType;
  preview?: string;
  diff?: string;
}

export interface WorkspaceDiff {
  id: string;
  title: string;
  timestamp: number;
  changes: FileChange[];
}
