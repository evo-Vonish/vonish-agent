import type { Conversation, MessageSegment, Model, ToolCall, UploadedFileMeta } from '@/types';

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

const STREAM_IDLE_TIMEOUT_MS = 45_000;

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

function normalizeUploadedFile(raw: any): UploadedFileMeta {
  const originalName = String(raw.originalName ?? raw.file_name ?? raw.fileName ?? 'unknown');
  const ext = String(raw.ext ?? (originalName.includes('.') ? originalName.split('.').pop() : '') ?? '').toLowerCase();
  return {
    id: String(raw.id ?? raw.file_id ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`),
    originalName,
    safeName: raw.safeName ?? raw.safe_name,
    mimeType: String(raw.mimeType ?? raw.mime_type ?? 'application/octet-stream'),
    ext,
    size: Number(raw.size ?? raw.file_size ?? 0),
    workspacePath: String(raw.workspacePath ?? raw.workspace_path ?? ''),
    createdAt: raw.createdAt ?? raw.created_at,
    status: (raw.status ?? 'failed') as UploadedFileMeta['status'],
    textExtracted: Boolean(raw.textExtracted ?? raw.text_extracted ?? false),
    textLength: Number(raw.textLength ?? raw.text_length ?? 0),
    textPreview: raw.textPreview ?? raw.text_preview,
    contextPolicy: raw.contextPolicy ?? raw.context_policy,
    contextText: raw.contextText ?? raw.context_text,
    resourceUri: raw.resourceUri ?? raw.resource_uri,
    error: raw.error,
  };
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

export interface SearchMatch {
  message_id: string;
  role: string;
  snippet: string;
  highlight_ranges: [number, number][];
}

export interface ConversationSearchResult {
  conversation_id: string;
  title: string;
  updated_at: string;
  matches: SearchMatch[];
}

export async function searchConversations(
  query: string,
): Promise<{ results: ConversationSearchResult[]; total: number }> {
  const response = await fetch(`/api/conversations/search?q=${encodeURIComponent(query)}`);
  if (!response.ok) throw new Error(`Search failed: HTTP ${response.status}`);
  return (await response.json()) as { results: ConversationSearchResult[]; total: number };
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

export async function summarizeConversationTitle(
  conversationId: string,
  model: string,
): Promise<string> {
  const response = await fetch(`/api/conversations/${conversationId}/summarize-title`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  });
  if (!response.ok) {
    throw new Error(`Failed to summarize conversation title: HTTP ${response.status}`);
  }
  const body = (await response.json()) as { title: string };
  return body.title;
}

export async function summarizeThinking(
  content: string,
  model: string,
): Promise<string> {
  const response = await fetch('/api/chat/thinking-summary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, model }),
  });
  if (!response.ok) {
    throw new Error(`Failed to summarize thinking: HTTP ${response.status}`);
  }
  const body = (await response.json()) as { summary: string };
  return body.summary;
}

export async function polishText(
  text: string,
  model: string,
): Promise<string> {
  const response = await fetch('/api/polish', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, model }),
  });
  if (!response.ok) {
    throw new Error(`Failed to polish text: HTTP ${response.status}`);
  }
  const body = (await response.json()) as { polished: string; original: string };
  return body.polished;
}

interface BackendMessage {
  role: string;
  content: string;
  thinking?: string | null;
  segments?: MessageSegment[] | null;
  tool_calls?: ToolCall[] | null;
  files?: UploadedFileMeta[] | null;
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

export async function uploadConversationFiles(
  conversationId: string,
  files: File[],
): Promise<{ uploaded: UploadedFileMeta[]; failed: UploadedFileMeta[]; total: number; successful: number }> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));

  const response = await fetch(`/api/uploads/${conversationId}`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => '');
    throw new Error(detail || `File upload failed: HTTP ${response.status}`);
  }

  const body = (await response.json()) as {
    uploaded: any[];
    failed: any[];
    total: number;
    successful: number;
  };
  return {
    uploaded: (body.uploaded ?? []).map(normalizeUploadedFile),
    failed: (body.failed ?? []).map(normalizeUploadedFile),
    total: body.total,
    successful: body.successful,
  };
}

export async function streamChat(
  conversationId: string,
  message: string,
  model: string,
  contextProfile: string,
  resources: UploadedFileMeta[],
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/chat/${conversationId}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      model,
      context_profile: contextProfile,
      enable_thinking: true,
      resources: resources.map((file) => ({
        uri: file.resourceUri,
        mime_type: file.mimeType,
        title: file.originalName,
        originalName: file.originalName,
        workspacePath: file.workspacePath,
        contextText: file.contextText,
        contextPolicy: file.contextPolicy,
        status: file.status,
        error: file.error,
      })),
    }),
    signal,
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => '');
    throw new Error(
      detail
        ? `Chat stream failed: HTTP ${response.status}: ${detail.slice(0, 1000)}`
        : `Chat stream failed: HTTP ${response.status}`,
    );
  }
  if (!response.body) {
    throw new Error('Chat stream did not return a response body.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const readWithTimeout = async () => {
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    try {
      return await Promise.race([
        reader.read(),
        new Promise<ReadableStreamReadResult<Uint8Array>>((_, reject) => {
          timeoutId = setTimeout(() => {
            void reader.cancel().catch(() => {});
            reject(new Error('Chat stream stalled: no data received for 45 seconds.'));
          }, STREAM_IDLE_TIMEOUT_MS);
        }),
      ]);
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
    }
  };

  while (true) {
    const { value, done } = await readWithTimeout();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split(/\r?\n\r?\n/);
    buffer = chunks.pop() ?? '';

    for (const chunk of chunks) {
      const parsed = parseSseChunk(chunk);
      if (parsed) {
        onEvent(parsed);
        if (parsed.event === 'error' || parsed.event === 'aborted') {
          await reader.cancel().catch(() => {});
          return;
        }
      }
    }
  }

  buffer += decoder.decode();
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

// ── Context Usage API ──────────────────────────────────────────────────

export interface ContextUsageData {
  conversation_id: string;
  total_tokens: number;
  max_tokens: number;
  available_budget: number;
  output_reserved: number;
  safety_margin: number;
  profile: string;
  model: string;
  usage_ratio: number;
  compression_level: string;
  budget_healthy: boolean;
  components: Record<string, number>;
  message_count: number;
  user_message_count: number;
  tool_call_count: number;
  workspace_file_count: number;
  memory_item_count: number;
}

export async function getContextUsage(
  conversationId: string,
  modelId: string,
  profileName = 'balanced',
): Promise<ContextUsageData> {
  const params = new URLSearchParams({ model_id: modelId, profile_name: profileName });
  const response = await fetch(`/api/context/${conversationId}/usage?${params}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch context usage: HTTP ${response.status}`);
  }
  return (await response.json()) as ContextUsageData;
}

export async function switchContextProfile(
  conversationId: string,
  profileName: string,
): Promise<{ status: string; profile: string }> {
  const response = await fetch(`/api/context/${conversationId}/profile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile: profileName }),
  });
  if (!response.ok) {
    throw new Error(`Failed to switch profile: HTTP ${response.status}`);
  }
  return (await response.json()) as { status: string; profile: string };
}

export async function compactContext(
  conversationId: string,
  profileName = 'balanced',
  modelId = 'deepseek-chat',
  level = 'medium',
): Promise<{ status: string; compression_level: string; tokens_saved: number; warnings: string[] }> {
  const params = new URLSearchParams({ profile_name: profileName, model_id: modelId, level });
  const response = await fetch(`/api/context/${conversationId}/compact?${params}`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Failed to compact context: HTTP ${response.status}`);
  }
  return (await response.json()) as { status: string; compression_level: string; tokens_saved: number; warnings: string[] };
}

// ── Tool Configuration API ────────────────────────────────────────────

export interface BackendTool {
  name: string;
  description: string;
  category: string;
  requires_confirmation: boolean;
  schema: Record<string, unknown>;
}

export async function listTools(): Promise<{ tools: BackendTool[]; total: number }> {
  const response = await fetch('/api/tools');
  if (!response.ok) throw new Error(`Failed to load tools: HTTP ${response.status}`);
  return (await response.json()) as { tools: BackendTool[]; total: number };
}

export async function fetchToolConfigs(): Promise<{ tools: Record<string, boolean> }> {
  const response = await fetch('/api/tools/config');
  if (!response.ok) throw new Error(`Failed to load tool configs: HTTP ${response.status}`);
  return (await response.json()) as { tools: Record<string, boolean> };
}

export async function enableTool(name: string): Promise<void> {
  const response = await fetch(`/api/tools/${encodeURIComponent(name)}/enable`, { method: 'POST' });
  if (!response.ok) throw new Error(`Failed to enable tool: HTTP ${response.status}`);
}

export async function disableTool(name: string): Promise<void> {
  const response = await fetch(`/api/tools/${encodeURIComponent(name)}/disable`, { method: 'POST' });
  if (!response.ok) throw new Error(`Failed to disable tool: HTTP ${response.status}`);
}

export async function fetchPromptPreview(): Promise<{
  token_estimate: number; hash: string; enabled_tools: string[];
  blocks: { id: string; type: string; tokens: number; enabled: boolean; source: string }[];
  content: string;
}> {
  const response = await fetch('/api/prompt/preview');
  if (!response.ok) throw new Error(`Failed to load prompt preview: HTTP ${response.status}`);
  return (await response.json()) as any;
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
