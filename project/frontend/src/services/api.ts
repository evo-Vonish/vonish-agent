import type { Conversation, Model } from '@/types';

interface BackendConversation {
  id: string;
  title: string;
  model: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

interface BackendModel {
  id: string;
  provider: string;
  context_window: number;
  max_output_tokens: number;
  supports_vision: boolean;
  supports_json_mode: boolean;
  supports_thinking: boolean;
  supports_context_cache: boolean;
  default_thinking_effort: string;
}

export interface StreamEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface ApiConfig {
  id: string;
  provider: 'deepseek' | 'kimi';
  name: string;
  apiBase: string;
  keyPreview: string;
  isDefault: boolean;
  createdAt: number;
  updatedAt: number;
}

interface BackendApiConfig {
  id: string;
  provider: 'deepseek' | 'kimi';
  name: string;
  api_base: string;
  key_preview: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

function toTimestamp(value: string): number {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? Date.now() : parsed;
}

function modelName(model: BackendModel): string {
  if (model.id === 'deepseek-v4-pro') return 'DeepSeek V4 Pro';
  if (model.id === 'deepseek-v4-flash') return 'DeepSeek V4 Flash';
  if (model.id === 'kimi-k2-6') return 'Kimi K2.6';
  if (model.id === 'kimi-k2-5') return 'Kimi K2.5';
  return model.id;
}

function modelDescription(model: BackendModel): string {
  const features = [
    model.supports_thinking ? 'thinking' : '',
    model.supports_vision ? 'vision' : '',
    model.supports_json_mode ? 'JSON' : '',
  ].filter(Boolean);
  return `${model.provider}${features.length ? ` · ${features.join(' · ')}` : ''}`;
}

export async function listModels(): Promise<Model[]> {
  const response = await fetch('/api/models');
  if (!response.ok) {
    throw new Error(`Failed to load models: HTTP ${response.status}`);
  }
  const body = (await response.json()) as { models: BackendModel[] };
  return body.models.map((model) => ({
    id: model.id,
    name: modelName(model),
    provider: model.provider,
    description: modelDescription(model),
    maxTokens: model.max_output_tokens,
    contextWindow: model.context_window,
    tags: [
      model.supports_thinking ? 'thinking' : '',
      model.supports_vision ? 'vision' : '',
    ].filter(Boolean),
  }));
}

export async function listConversations(): Promise<Conversation[]> {
  const response = await fetch('/api/conversations');
  if (!response.ok) {
    throw new Error(`Failed to load conversations: HTTP ${response.status}`);
  }
  const body = (await response.json()) as {
    conversations: BackendConversation[];
  };
  return body.conversations.map((conversation) => ({
    id: conversation.id,
    title: conversation.title,
    messages: [],
    model: conversation.model,
    createdAt: toTimestamp(conversation.created_at),
    updatedAt: toTimestamp(conversation.updated_at),
    messageCount: conversation.message_count,
  }));
}

export async function createConversation(
  title: string,
  model: string,
): Promise<Conversation> {
  const response = await fetch('/api/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title,
      model,
      context_profile: 'balanced',
    }),
  });
  if (!response.ok) {
    throw new Error(`Failed to create conversation: HTTP ${response.status}`);
  }
  const conversation = (await response.json()) as BackendConversation;
  return {
    id: conversation.id,
    title: conversation.title,
    messages: [],
    model: conversation.model,
    createdAt: toTimestamp(conversation.created_at),
    updatedAt: toTimestamp(conversation.updated_at),
    messageCount: conversation.message_count,
  };
}

export async function deleteConversation(id: string): Promise<void> {
  const response = await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
  if (!response.ok && response.status !== 404) {
    throw new Error(`Failed to delete conversation: HTTP ${response.status}`);
  }
}

interface BackendMessage {
  role: string;
  content: string;
  thinking?: string | null;
  timestamp: string;
}

export async function getConversationMessages(
  conversationId: string,
): Promise<{ messages: BackendMessage[]; conversation_id: string }> {
  const response = await fetch(`/api/conversations/${conversationId}/messages`);
  if (!response.ok) {
    throw new Error(`Failed to load messages: HTTP ${response.status}`);
  }
  return (await response.json()) as {
    messages: BackendMessage[];
    conversation_id: string;
  };
}

/** Backend workspace file entry */
export interface WorkspaceFileItem {
  name: string;
  path: string;
  type: 'file' | 'folder';
  size?: number;
  modified_at?: string;
  mime_type?: string;
}

/**
 * List files in a conversation's workspace.
 * Returns a flat list — frontend builds the tree.
 */
export async function listWorkspaceFiles(
  conversationId: string,
  subdir?: string,
): Promise<WorkspaceFileItem[]> {
  const params = new URLSearchParams();
  if (subdir) params.set('path', subdir);
  const qs = params.toString();
  const url = `/api/workspaces/${conversationId}/files${qs ? `?${qs}` : ''}`;
  const response = await fetch(url);
  if (!response.ok) {
    // Workspace may not exist yet — return empty
    return [];
  }
  const body = (await response.json()) as { files: WorkspaceFileItem[] };
  return body.files;
}

/**
 * Call backend to stop/interrupt an ongoing chat stream.
 */
export async function stopChat(conversationId: string): Promise<void> {
  await fetch(`/api/chat/${conversationId}/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: 'user_request' }),
  });
}

export async function streamChat(
  conversationId: string,
  message: string,
  model: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/chat/${conversationId}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      model,
      enable_thinking: true,
      resources: [],
    }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Chat stream failed: HTTP ${response.status}`);
  }
  if (!response.body) {
    throw new Error('Chat stream did not return a response body.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split(/\r?\n\r?\n/);
    buffer = chunks.pop() ?? '';

    for (const chunk of chunks) {
      const parsed = parseSseChunk(chunk);
      if (parsed) onEvent(parsed);
    }
  }

  if (buffer.trim()) {
    const parsed = parseSseChunk(buffer);
    if (parsed) onEvent(parsed);
  }
}

function toApiConfig(config: BackendApiConfig): ApiConfig {
  return {
    id: config.id,
    provider: config.provider,
    name: config.name,
    apiBase: config.api_base,
    keyPreview: config.key_preview,
    isDefault: config.is_default,
    createdAt: toTimestamp(config.created_at),
    updatedAt: toTimestamp(config.updated_at),
  };
}

export async function listApiConfigs(): Promise<ApiConfig[]> {
  const response = await fetch('/api/api-configs');
  if (!response.ok) {
    throw new Error(`Failed to load API configs: HTTP ${response.status}`);
  }
  const body = (await response.json()) as { configs: BackendApiConfig[] };
  return body.configs.map(toApiConfig);
}

export async function createApiConfig(input: {
  provider: 'deepseek' | 'kimi';
  name: string;
  apiBase: string;
  apiKey: string;
  isDefault: boolean;
}): Promise<ApiConfig> {
  const response = await fetch('/api/api-configs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      provider: input.provider,
      name: input.name,
      api_base: input.apiBase,
      api_key: input.apiKey,
      is_default: input.isDefault,
    }),
  });
  if (!response.ok) {
    throw new Error(`Failed to save API config: HTTP ${response.status}`);
  }
  return toApiConfig((await response.json()) as BackendApiConfig);
}

export async function updateApiConfig(
  id: string,
  input: {
    name: string;
    apiBase: string;
    apiKey?: string;
    isDefault?: boolean;
  },
): Promise<ApiConfig> {
  const response = await fetch(`/api/api-configs/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: input.name,
      api_base: input.apiBase,
      api_key: input.apiKey || undefined,
      is_default: input.isDefault,
    }),
  });
  if (!response.ok) {
    throw new Error(`Failed to update API config: HTTP ${response.status}`);
  }
  return toApiConfig((await response.json()) as BackendApiConfig);
}

export async function deleteApiConfig(id: string): Promise<void> {
  const response = await fetch(`/api/api-configs/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(`Failed to delete API config: HTTP ${response.status}`);
  }
}

export async function setDefaultApiConfig(id: string): Promise<ApiConfig> {
  const response = await fetch(`/api/api-configs/${id}/default`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Failed to set default API config: HTTP ${response.status}`);
  }
  return toApiConfig((await response.json()) as BackendApiConfig);
}

function parseSseChunk(chunk: string): StreamEvent | null {
  let event = 'message';
  const dataLines: string[] = [];

  for (const line of chunk.split(/\r?\n/)) {
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart());
    }
  }

  if (dataLines.length === 0) return null;

  try {
    return {
      event,
      data: JSON.parse(dataLines.join('\n')) as Record<string, unknown>,
    };
  } catch {
    return {
      event,
      data: { content: dataLines.join('\n') },
    };
  }
}
