export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  type?: 'text' | 'thinking' | 'tool_call' | 'tool_result' | 'error';
  thinkingContent?: string;
  thinkingBlocks?: string[];  // per-round thinking blocks (each round = one card)
  toolCalls?: ToolCall[];
  timestamp: number;
  status?: 'sending' | 'streaming' | 'complete' | 'error';
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
