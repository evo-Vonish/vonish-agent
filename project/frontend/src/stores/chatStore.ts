import { create } from 'zustand';
import type {
  Message,
  Conversation,
  Model,
  ContextProfile,
  ContextUsage,
  ExecutionSegment,
  ExecutionStep,
  ToolCall,
  MessageSegment,
  UploadedFileMeta,
  WorkflowError,
} from '@/types';
import { contextProfiles } from '@/services/mockData';
import {
  createConversation as apiCreateConversation,
  createProject as apiCreateProject,
  deleteAllConversations as apiDeleteAllConversations,
  deleteConversation as apiDeleteConversation,
  deleteProject as apiDeleteProject,
  listConversations,
  listModels,
  renameProject as apiRenameProject,
  streamChat,
  stopChat,
  getConversationMessages,
  summarizeConversationTitle,
  summarizeThinking,
  getContextUsage,
  uploadConversationFiles,
} from '@/services/api';
import { generateId } from '@/lib/utils';
import { useWorkspaceStore } from './workspaceStore';
import { useToolStore } from './useToolStore';
import { useSessionDraftStore } from './sessionDraftStore';
import { useReferenceStore } from './referenceStore';
import { useContextToastStore } from './contextToastStore';
import { useWorkbenchStore } from './workbenchStore';

type InteractiveToolType = 'ask_user_question' | 'request_approval';

const MAX_ATTACHMENTS = 10;
const MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024;
const MAX_TOTAL_ATTACHMENT_SIZE = 50 * 1024 * 1024;
const WORKFLOW_AUTO_RESUME_PROMPT =
  '继续执行当前任务，从上一次未完成的位置恢复。不要要求用户重复需求，不要重复已经完成的工作，直接继续完成任务。';
const MAX_WORKFLOW_AUTO_RESUMES = 3;
const ALLOWED_ATTACHMENT_EXTENSIONS = new Set([
  'txt',
  'md',
  'markdown',
  'pdf',
  'doc',
  'docx',
  'ppt',
  'pptx',
  'jpg',
  'jpeg',
  'png',
  'webp',
  'gif',
]);

interface PendingInteractionOption {
  id: string;
  label: string;
  description?: string;
}

interface PendingInteraction {
  type: InteractiveToolType;
  toolCallId: string;
  interactionId: string;
  title?: string;
  message: string;
  options?: string[];
  optionItems?: PendingInteractionOption[];
  allowCustom?: boolean;
  riskLevel?: 'low' | 'medium' | 'high';
  plan?: { id: string; title: string; description?: string; risk?: string }[];
}

interface SendMessageOptions {
  internalContinue?: boolean;
  autoResumeDepth?: number;
}

interface ChatState {
  conversations: Conversation[];
  currentConversationId: string | null;
  messages: Message[];
  models: Model[];
  selectedModelId: string;
  contextProfile: ContextProfile;
  availableProfiles: ContextProfile[];
  contextUsage: ContextUsage | null;
  isStreaming: boolean;
  inputText: string;
  attachments: { id: string; file: File; uploading: boolean }[];
  suggestions: string[];
  apiError: string | null;
  initialized: boolean;
  _abortController: AbortController | null;
  pendingInteraction: PendingInteraction | null;

  initialize: () => Promise<void>;
  setInputText: (text: string) => void;
  addMessage: (msg: Message) => void;
  updateMessage: (id: string, partial: Partial<Message>) => void;
  sendMessage: (content: string, options?: SendMessageOptions) => Promise<void>;
  resumeWorkflow: (prompt?: string) => Promise<void>;
  stopGeneration: () => void;
  respondToInteraction: (choice: string, message?: string) => Promise<void>;
  selectConversation: (id: string) => Promise<void>;
  createConversation: (title?: string) => Promise<string>;
  createProject: (input: { name: string; directoryPath?: string }) => Promise<string>;
  deleteConversation: (id: string) => Promise<void>;
  renameProject: (projectId: string, name: string) => Promise<void>;
  deleteProject: (projectId: string) => Promise<void>;
  clearAll: () => Promise<void>;
  setSelectedModel: (id: string) => void;
  setContextProfile: (profile: ContextProfile) => void;
  switchContextProfile: (profileId: string) => void;
  fetchContextUsage: () => Promise<void>;
  setIsStreaming: (v: boolean) => void;
  addAttachment: (file: File) => void;
  removeAttachment: (id: string) => void;
  clearAttachments: () => void;
  setSuggestions: (suggestions: string[]) => void;
  clearApiError: () => void;
  clearMessages: () => void;
}

const fallbackModels: Model[] = [
  {
    id: 'deepseek-v4-flash',
    name: 'DeepSeek V4 Flash',
    provider: 'deepseek',
    description: 'Fast DeepSeek chat model',
    maxTokens: 8192,
    contextWindow: 256_000,
    tags: ['chat'],
  },
  {
    id: 'deepseek-v4-pro',
    name: 'DeepSeek V4 Pro',
    provider: 'deepseek',
    description: 'DeepSeek reasoning model',
    maxTokens: 8192,
    contextWindow: 256_000,
    tags: ['thinking'],
  },
  {
    id: 'kimi-k2-6',
    name: 'Kimi K2.6',
    provider: 'kimi',
    description: 'Kimi thinking model',
    maxTokens: 8192,
    contextWindow: 256_000,
    tags: ['thinking', 'vision'],
  },
  {
    id: 'kimi-k2-5',
    name: 'Kimi K2.5',
    provider: 'kimi',
    description: 'Kimi thinking model',
    maxTokens: 8192,
    contextWindow: 256_000,
    tags: ['thinking', 'vision'],
  },
];

function appendMessageToConversation(
  conversations: Conversation[],
  conversationId: string | null,
  messages: Message[],
): Conversation[] {
  if (!conversationId) return conversations;
  return conversations.map((conversation) =>
    conversation.id === conversationId
      ? {
          ...conversation,
          messages,
          messageCount: messages.length,
          updatedAt: Date.now(),
        }
      : conversation,
  );
}

function firstLineTitle(content: string): string {
  const compact = content.replace(/\s+/g, ' ').trim();
  return compact.length > 36 ? `${compact.slice(0, 36)}...` : compact || 'New chat';
}

function compactPhrase(content: string): string {
  const compact = content.replace(/\s+/g, ' ').trim();
  if (!compact) return '思考过程';
  const sentence = compact.split(/[。！？.!?]/)[0]?.trim() || compact;
  return sentence.length > 18 ? `${sentence.slice(0, 18)}...` : sentence;
}

function queuedFileMeta(attachment: { id: string; file: File; uploading: boolean }): UploadedFileMeta {
  const ext = attachment.file.name.includes('.')
    ? attachment.file.name.split('.').pop()?.toLowerCase() || ''
    : '';
  return {
    id: attachment.id,
    originalName: attachment.file.name,
    mimeType: attachment.file.type || 'application/octet-stream',
    ext,
    size: attachment.file.size,
    workspacePath: '',
    status: attachment.uploading ? 'uploading' : 'queued',
  };
}

function validateAttachment(file: File, existing: { file: File }[]): string | null {
  const ext = file.name.includes('.') ? file.name.split('.').pop()?.toLowerCase() || '' : '';
  if (!ALLOWED_ATTACHMENT_EXTENSIONS.has(ext)) {
    return `不支持的文件类型：${file.name}`;
  }
  if (file.size > MAX_ATTACHMENT_SIZE) {
    return `文件过大：${file.name}`;
  }
  if (existing.length >= MAX_ATTACHMENTS) {
    return `单次最多上传 ${MAX_ATTACHMENTS} 个文件`;
  }
  const total = existing.reduce((sum, item) => sum + item.file.size, 0) + file.size;
  if (total > MAX_TOTAL_ATTACHMENT_SIZE) {
    return '文件总大小超过 50MB';
  }
  return null;
}

function isInteractiveToolName(toolName: string): toolName is InteractiveToolType {
  return toolName === 'ask_user_question' || toolName === 'request_approval';
}

function normalizeInteractionOptions(raw: unknown): PendingInteractionOption[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((option, index) => {
      if (typeof option === 'string') {
        return { id: option, label: option };
      }
      if (option && typeof option === 'object') {
        const source = option as Record<string, unknown>;
        const label = String(source.label ?? source.id ?? `Option ${index + 1}`);
        return {
          id: String(source.id ?? label),
          label,
          description: source.description ? String(source.description) : undefined,
        };
      }
      return null;
    })
    .filter((option): option is PendingInteractionOption => Boolean(option));
}

function normalizePendingInteraction(
  raw: Record<string, unknown>,
  toolCallId = '',
): PendingInteraction | null {
  const interaction =
    raw.interaction && typeof raw.interaction === 'object'
      ? (raw.interaction as Record<string, unknown>)
      : raw;
  const payload =
    interaction.payload && typeof interaction.payload === 'object'
      ? (interaction.payload as Record<string, unknown>)
      : {};
  const type = String(interaction.type ?? raw.type ?? '');
  if (!isInteractiveToolName(type)) return null;

  const optionItems = normalizeInteractionOptions(interaction.options ?? payload.options);
  const plan = Array.isArray(interaction.plan)
    ? interaction.plan
    : Array.isArray(payload.plan)
      ? payload.plan
      : undefined;
  const risk = String(interaction.risk_level ?? payload.risk_level ?? 'medium');

  return {
    type,
    toolCallId,
    interactionId: String(interaction.id ?? interaction.interaction_id ?? raw.interaction_id ?? toolCallId),
    title: interaction.title ? String(interaction.title) : undefined,
    message: String(interaction.description ?? interaction.message ?? raw.description ?? raw.message ?? ''),
    options: optionItems.map((option) => option.label),
    optionItems,
    allowCustom: Boolean(interaction.allow_custom_response ?? payload.allow_custom_response ?? true),
    riskLevel: risk === 'low' || risk === 'medium' || risk === 'high' ? risk : 'medium',
    plan: Array.isArray(plan) ? (plan as PendingInteraction['plan']) : undefined,
  };
}

function updateSegment(
  segments: MessageSegment[] | undefined,
  segmentId: string,
  updater: (segment: MessageSegment) => MessageSegment,
): MessageSegment[] {
  return (segments ?? []).map((segment) =>
    segment.id === segmentId ? updater(segment) : segment,
  );
}

function optionalNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function executionStatus(value: unknown): ExecutionSegment['status'] {
  const status = String(value ?? '');
  if (
    status === 'running' ||
    status === 'completed' ||
    status === 'failed' ||
    status === 'cancelled' ||
    status === 'waiting_user'
  ) {
    return status;
  }
  return 'running';
}

function executionStepStatus(value: unknown): ExecutionStep['status'] {
  const status = String(value ?? '');
  if (
    status === 'running' ||
    status === 'completed' ||
    status === 'failed' ||
    status === 'cancelled' ||
    status === 'skipped' ||
    status === 'retrying'
  ) {
    return status;
  }
  return 'running';
}

function executionStepType(value: unknown): ExecutionStep['type'] {
  const type = String(value ?? '');
  if (
    type === 'thinking' ||
    type === 'tool_call' ||
    type === 'tool_result' ||
    type === 'file_read' ||
    type === 'file_write' ||
    type === 'file_edit' ||
    type === 'command' ||
    type === 'web_search' ||
    type === 'web_fetch' ||
    type === 'research' ||
    type === 'recall' ||
    type === 'user_interaction' ||
    type === 'system_notice' ||
    type === 'error_notice'
  ) {
    return type;
  }
  return 'tool_call';
}

function numberCount(value: unknown): number {
  return optionalNumber(value) ?? 0;
}

function normalizeWorkflowError(raw: unknown, fallbackSegmentId?: string): WorkflowError {
  const source = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const actions = Array.isArray(source.actions)
    ? source.actions.reduce<WorkflowError['actions']>((items, item) => {
          const action = item && typeof item === 'object' ? (item as Record<string, unknown>) : {};
          const id = String(action.id ?? '').trim();
          const label = String(action.label ?? '').trim();
          if (!id || !label) return items;
          const rawStyle = String(action.style ?? 'secondary');
          items.push({
            id,
            label,
            style:
              rawStyle === 'primary' || rawStyle === 'secondary' || rawStyle === 'danger'
                ? rawStyle
                : 'secondary',
          });
          return items;
        }, [])
    : [];
  const severity = String(source.severity ?? 'error');
  return {
    id: String(source.id || source.errorId || `workflow-error-${generateId()}`),
    segmentId: source.segmentId ? String(source.segmentId) : fallbackSegmentId,
    stepId: source.stepId ? String(source.stepId) : undefined,
    severity:
      severity === 'info' || severity === 'warning' || severity === 'error' || severity === 'fatal'
        ? severity
        : 'error',
    errorType: String(source.errorType ?? 'workflow_error'),
    title: String(source.title ?? '工作流异常'),
    message: String(source.message ?? '处理流程异常中断。'),
    recoverable: Boolean(source.recoverable ?? true),
    actions,
    detailsRef: source.detailsRef ? String(source.detailsRef) : undefined,
  };
}

function normalizeExecutionStep(raw: unknown, segmentId: string): ExecutionStep {
  const source = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  return {
    id: String(source.id || source.stepId || `step-${generateId()}`),
    segmentId: String(source.segmentId || segmentId),
    type: executionStepType(source.type ?? source.stepType),
    status: executionStepStatus(source.status),
    title: String(source.title || '执行步骤'),
    subtitle: source.subtitle ? String(source.subtitle) : undefined,
    startedAt: source.startedAt ? String(source.startedAt) : undefined,
    endedAt: source.endedAt ? String(source.endedAt) : undefined,
    durationMs: optionalNumber(source.durationMs),
    toolName: source.toolName ? String(source.toolName) : undefined,
    toolCallId: source.toolCallId ? String(source.toolCallId) : undefined,
    inputPreview: source.inputPreview ? String(source.inputPreview) : undefined,
    outputPreview: source.outputPreview ? String(source.outputPreview) : undefined,
    content: source.content ? String(source.content) : undefined,
    error: source.error ? String(source.error) : undefined,
    metadata:
      source.metadata && typeof source.metadata === 'object'
        ? (source.metadata as Record<string, unknown>)
        : undefined,
    collapsible: Boolean(source.collapsible ?? true),
    defaultCollapsed: Boolean(source.defaultCollapsed ?? source.status !== 'running'),
    raw: source.raw,
  };
}

function normalizeExecutionSegment(raw: unknown): ExecutionSegment {
  const source = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const id = String(source.id || source.segmentId || `segment-${generateId()}`);
  const steps = Array.isArray(source.steps)
    ? source.steps.map((step) => normalizeExecutionStep(step, id))
    : [];
  const errors = Array.isArray(source.errors)
    ? source.errors.map((error) => normalizeWorkflowError(error, id))
    : [];
  return {
    id,
    status: executionStatus(source.status),
    title: source.title ? String(source.title) : '处理区间',
    goal: source.goal ? String(source.goal) : undefined,
    startedAt: source.startedAt ? String(source.startedAt) : undefined,
    endedAt: source.endedAt ? String(source.endedAt) : undefined,
    durationMs: optionalNumber(source.durationMs),
    thinkingCount: numberCount(source.thinkingCount),
    toolCallCount: numberCount(source.toolCallCount),
    commandCount: numberCount(source.commandCount),
    fileReadCount: numberCount(source.fileReadCount),
    fileWriteCount: numberCount(source.fileWriteCount),
    fileEditCount: numberCount(source.fileEditCount),
    webRequestCount: numberCount(source.webRequestCount),
    recallCount: numberCount(source.recallCount),
    errorCount: numberCount(source.errorCount),
    totalTokens: optionalNumber(source.totalTokens),
    steps,
    errors,
    summary: source.summary ? String(source.summary) : undefined,
    collapsible: Boolean(source.collapsible ?? true),
    defaultCollapsed: Boolean(source.defaultCollapsed ?? source.status !== 'running'),
  };
}

function createWorkflowErrorSegment(
  raw: unknown,
  fallback: {
    title?: string;
    message?: string;
    errorType?: string;
    severity?: WorkflowError['severity'];
  } = {},
): Extract<MessageSegment, { type: 'workflow_error' }> {
  const error = normalizeWorkflowError(
    {
      title: fallback.title ?? '工作流已中断',
      message: fallback.message ?? '处理流程异常中断。',
      errorType: fallback.errorType ?? 'workflow_error',
      severity: fallback.severity ?? 'error',
      recoverable: true,
      actions: [
        { id: 'continue_task', label: '继续任务', style: 'primary' },
        { id: 'copy_error', label: '复制错误', style: 'secondary' },
      ],
      ...(raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}),
    },
  );
  return {
    id: `workflow-error-${error.id}`,
    type: 'workflow_error',
    error,
    retryPrompt:
      WORKFLOW_AUTO_RESUME_PROMPT,
  };
}

function normalizeToolCall(raw: unknown): ToolCall {
  const source = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const rawStatus = String(source.status ?? '');
  const status: ToolCall['status'] =
    rawStatus === 'pending' ||
    rawStatus === 'running' ||
    rawStatus === 'success' ||
    rawStatus === 'error'
      ? rawStatus
      : 'pending';
  const args =
    source.arguments && typeof source.arguments === 'object' && !Array.isArray(source.arguments)
      ? (source.arguments as Record<string, unknown>)
      : {};
  const tool: ToolCall = {
    id: String(source.id || generateId()),
    name: String(source.name || ''),
    arguments: args,
    status,
  };
  if ('result' in source) tool.result = source.result;
  if (source.error !== undefined && source.error !== null) tool.error = String(source.error);
  const duration = optionalNumber(source.duration);
  if (duration !== undefined) tool.duration = duration;
  const startTime = optionalNumber(source.startTime);
  if (startTime !== undefined) tool.startTime = startTime;
  return tool;
}

function normalizeArtifactRef(raw: unknown, fallbackWorkspaceId?: string | null) {
  const source = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  const artifactSource =
    source.artifact && typeof source.artifact === 'object'
      ? (source.artifact as Record<string, unknown>)
      : source;
  const path = String(artifactSource.path ?? artifactSource.workspacePath ?? '');
  const title = String(artifactSource.title ?? artifactSource.name ?? path.split(/[\\/]/).pop() ?? 'Artifact');
  return {
    id: String(artifactSource.id ?? source.call_id ?? path ?? generateId()),
    title,
    path,
    workspaceId:
      artifactSource.workspaceId === undefined && source.workspace_id === undefined
        ? fallbackWorkspaceId ?? null
        : String(artifactSource.workspaceId ?? source.workspace_id ?? fallbackWorkspaceId ?? ''),
    mimeType: artifactSource.mimeType ? String(artifactSource.mimeType) : artifactSource.mime_type ? String(artifactSource.mime_type) : undefined,
    kind: artifactSource.kind ? String(artifactSource.kind) : undefined,
    size: optionalNumber(artifactSource.size),
    sourceToolCallId: artifactSource.sourceToolCallId ? String(artifactSource.sourceToolCallId) : source.call_id ? String(source.call_id) : undefined,
    description: artifactSource.description ? String(artifactSource.description) : undefined,
  };
}

function normalizeAssistantSegments(
  rawSegments: MessageSegment[] | null | undefined,
  thinking: string | null | undefined,
  content: string,
): MessageSegment[] {
  if (Array.isArray(rawSegments) && rawSegments.length > 0) {
    const normalized: MessageSegment[] = [];
    rawSegments.forEach((segment, index) => {
      const source = segment as unknown as Record<string, unknown>;
      if (source.type === 'thinking') {
        const text = String(source.content ?? '');
        normalized.push({
          id: String(source.id || `thinking-${index}`),
          type: 'thinking',
          content: text,
          summary: source.summary ? String(source.summary) : compactPhrase(text),
          status: 'complete',
        });
      } else if (source.type === 'text') {
        normalized.push({
          id: String(source.id || `text-${index}`),
          type: 'text',
          content: String(source.content ?? ''),
        });
      } else if (source.type === 'tool') {
        const tool = normalizeToolCall(source.tool);
        normalized.push({
          id: String(source.id || `tool-${tool.id}`),
          type: 'tool',
          tool,
        });
      } else if (source.type === 'execution') {
        const execution = normalizeExecutionSegment(source.execution ?? source);
        normalized.push({
          id: String(source.id || `execution-${execution.id}`),
          type: 'execution',
          execution,
        });
      } else if (source.type === 'workflow_error') {
        normalized.push({
          ...createWorkflowErrorSegment(source.error ?? source),
          id: String(source.id || `workflow-error-${index}`),
          retryPrompt: source.retryPrompt ? String(source.retryPrompt) : undefined,
        });
      } else if (source.type === 'artifact' && source.artifact && typeof source.artifact === 'object') {
        const artifact = source.artifact as Record<string, unknown>;
        normalized.push({
          id: String(source.id || `artifact-${index}`),
          type: 'artifact',
          artifact: {
            id: String(artifact.id || artifact.path || generateId()),
            title: String(artifact.title || artifact.path || 'Artifact'),
            path: String(artifact.path || ''),
            workspaceId: artifact.workspaceId === undefined || artifact.workspaceId === null ? null : String(artifact.workspaceId),
            mimeType: artifact.mimeType ? String(artifact.mimeType) : undefined,
            kind: artifact.kind ? String(artifact.kind) : undefined,
            size: optionalNumber(artifact.size),
            sourceToolCallId: artifact.sourceToolCallId ? String(artifact.sourceToolCallId) : undefined,
            description: artifact.description ? String(artifact.description) : undefined,
          },
        });
      }
    });
    return normalized;
  }

  return [
    ...(thinking
      ? [
          {
            id: generateId(),
            type: 'thinking' as const,
            content: thinking,
            summary: compactPhrase(thinking),
            status: 'complete' as const,
          },
        ]
      : []),
    ...(content ? [{ id: generateId(), type: 'text' as const, content }] : []),
  ];
}

function projectErrorMessage(raw: unknown, fallback: Parameters<typeof createWorkflowErrorSegment>[1]): Message {
  const segment = createWorkflowErrorSegment(raw, fallback);
  return {
    id: generateId(),
    role: 'system',
    content: segment.error.message,
    type: 'error',
    segments: [segment],
    timestamp: Date.now(),
    status: 'error',
  };
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  currentConversationId: null,
  messages: [],
  models: fallbackModels,
  selectedModelId: fallbackModels[0].id,
  contextProfile: contextProfiles.find((p) => p.id === 'balanced') ?? contextProfiles[0],
  availableProfiles: contextProfiles,
  contextUsage: null,
  isStreaming: false,
  inputText: '',
  attachments: [],
  suggestions: [],
  apiError: null,
  initialized: false,
  _abortController: null,
  pendingInteraction: null,

  initialize: async () => {
    if (get().initialized) return;
    try {
      const [models, conversations] = await Promise.all([
        listModels(),
        listConversations(),
      ]);
      set((state) => {
        const selectedModelId =
          models.find((model) => model.id === state.selectedModelId)?.id ??
          models[0]?.id ??
          state.selectedModelId;
        const currentConversationId =
          state.currentConversationId ?? conversations[0]?.id ?? null;
        const currentConversation = conversations.find(
          (conversation) => conversation.id === currentConversationId,
        );
        return {
          models: models.length ? models : state.models,
          selectedModelId,
          conversations,
          currentConversationId,
          messages: [],
          initialized: true,
          apiError: null,
        };
      });
      // Load messages and workspace for initial conversation
      const cid = get().currentConversationId;
      if (cid) {
        // Load actual messages from DB
        try {
          const result = await getConversationMessages(cid);
          const msgs: Message[] = result.messages.map((m) => {
            const role = m.role as 'user' | 'assistant';
            const segments =
              role === 'assistant'
                ? normalizeAssistantSegments(m.segments, m.thinking, m.content)
                : [];
            const segmentToolCalls = segments
              .filter((segment): segment is Extract<MessageSegment, { type: 'tool' }> =>
                segment.type === 'tool',
              )
              .map((segment) => segment.tool);
            const persistedToolCalls = Array.isArray(m.tool_calls)
              ? m.tool_calls.map((tool) => normalizeToolCall(tool))
              : [];
            const toolCalls = segmentToolCalls.length ? segmentToolCalls : persistedToolCalls;
            return {
              id: generateId(),
              role,
              content: m.content,
              thinkingContent: m.thinking ?? undefined,
              segments: segments.length ? segments : undefined,
              toolCalls: toolCalls.length ? toolCalls : undefined,
              files: m.files ?? undefined,
              references: m.references ?? undefined,
              type: 'text',
              timestamp: Date.parse(m.timestamp) || Date.now(),
              status: 'complete' as const,
            };
          });
          set({ messages: msgs });
        } catch {
          set({ messages: [] });
        }
        useWorkspaceStore.getState().loadWorkspace(cid);
        void get().fetchContextUsage();
      }
      // Load tools from backend
      void useToolStore.getState().loadToolsFromBackend();
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      set((state) => ({
        initialized: true,
        apiError: detail,
        messages: [
          ...state.messages,
          projectErrorMessage(error, {
            title: '项目初始化失败',
            message: detail,
            errorType: 'initialize_error',
            severity: 'error',
          }),
        ],
      }));
    }
  },

  setInputText: (text) => set({ inputText: text }),

  addMessage: (msg) =>
    set((state) => {
      const messages = [...state.messages, msg];
      return {
        messages,
        conversations: appendMessageToConversation(
          state.conversations,
          state.currentConversationId,
          messages,
        ),
      };
    }),

  updateMessage: (id, partial) =>
    set((state) => {
      const messages = state.messages.map((message) =>
        message.id === id ? { ...message, ...partial } : message,
      );
      return {
        messages,
        conversations: appendMessageToConversation(
          state.conversations,
          state.currentConversationId,
          messages,
        ),
      };
    }),

  sendMessage: async (content, options = {}) => {
    if (get().isStreaming) return;
    const usage = get().contextUsage;
    if (usage && usage.totalTokens >= usage.maxTokens) {
      set({ apiError: '上下文已达到固定 256K 限制，请新建对话后继续。' });
      return;
    }
    const internalContinue = Boolean(options.internalContinue);
    const attachmentSnapshot = internalContinue ? [] : get().attachments;
    const hasAttachments = attachmentSnapshot.length > 0;
    const referenceList = internalContinue ? [] : useReferenceStore.getState().references;
    const trimmedContent = content.trim();
    if (!trimmedContent && !hasAttachments && referenceList.length === 0) return;

    let conversationId = get().currentConversationId;
    if (!conversationId) {
      conversationId = await get().createConversation(
        firstLineTitle(trimmedContent || attachmentSnapshot[0]?.file.name || 'File upload'),
      );
    }

    let userMsg: Message | null = null;
    if (!internalContinue) {
      userMsg = {
        id: generateId(),
        role: 'user',
        content: trimmedContent,
        type: 'text',
        files: attachmentSnapshot.map(queuedFileMeta),
        references: referenceList,
        timestamp: Date.now(),
        status: 'complete',
      };
      get().addMessage(userMsg);
      set({ attachments: [] });
      useReferenceStore.getState().clearReferences();
    }

    const assistantMsg: Message = {
      id: generateId(),
      role: 'assistant',
      content: '',
      type: 'text',
      timestamp: Date.now(),
      status: 'streaming',
    };
    get().addMessage(assistantMsg);
    const abort = new AbortController();
    set({ isStreaming: true, apiError: null, pendingInteraction: null, _abortController: abort });

    const currentMsgId = assistantMsg.id;
    const selectedModelForRequest = get().selectedModelId;
    const sessionDraft = useSessionDraftStore.getState();
    const currentConversation = get().conversations.find((conversation) => conversation.id === conversationId);
    const selectedWorkspaceId = String(
      currentConversation?.metadata?.workspace_id ||
      currentConversation?.metadata?.project_id ||
      conversationId,
    );
    let activeThinkingSegmentId: string | null = null;
    let activeTextSegmentId: string | null = null;
    let activeExecutionSegmentId: string | null = null;
    let structuredExecutionActive = false;
    let shouldAutoResumeWorkflow = false;

    const appendSegment = (segment: MessageSegment) => {
      const current = get().messages.find((m) => m.id === currentMsgId);
      get().updateMessage(currentMsgId, {
        segments: [...(current?.segments ?? []), segment],
      });
    };

    const updateSegments = (
      segmentId: string,
      updater: (segment: MessageSegment) => MessageSegment,
    ) => {
      const current = get().messages.find((m) => m.id === currentMsgId);
      get().updateMessage(currentMsgId, {
        segments: updateSegment(current?.segments, segmentId, updater),
      });
    };

    const updateExecutionSegment = (
      segmentId: string,
      updater: (segment: ExecutionSegment) => ExecutionSegment,
    ) => {
      updateSegments(`execution-${segmentId}`, (segment) =>
        segment.type === 'execution'
          ? { ...segment, execution: updater(segment.execution) }
          : segment,
      );
    };

    const upsertExecutionStep = (segmentId: string, step: ExecutionStep) => {
      updateExecutionSegment(segmentId, (segment) => {
        const index = segment.steps.findIndex((item) => item.id === step.id);
        const steps =
          index >= 0
            ? segment.steps.map((item) => (item.id === step.id ? { ...item, ...step } : item))
            : [...segment.steps, step];
        return { ...segment, steps };
      });
    };

    const appendWorkflowError = (segmentId: string, error: WorkflowError) => {
      updateExecutionSegment(segmentId, (segment) => ({
        ...segment,
        status: 'failed',
        errorCount: Math.max(segment.errorCount, (segment.errors?.length ?? 0) + 1),
        errors: [...(segment.errors ?? []), error],
        steps: [
          ...segment.steps,
          {
            id: `error-step-${error.id}`,
            segmentId,
            type: 'error_notice',
            status: 'failed',
            title: error.title,
            subtitle: error.message,
            error: error.message,
            collapsible: true,
            defaultCollapsed: false,
          },
        ],
      }));
    };

    const appendMessageWorkflowError = (raw: unknown, fallback?: Parameters<typeof createWorkflowErrorSegment>[1]) => {
      appendSegment(createWorkflowErrorSegment(raw, fallback));
    };

    try {
      let uploadedFiles: UploadedFileMeta[] = [];
      if (selectedWorkspaceId) {
        await useWorkspaceStore.getState().selectWorkspace(selectedWorkspaceId);
      }
      if (hasAttachments) {
        const uploadResult = await uploadConversationFiles(
          conversationId,
          attachmentSnapshot.map((attachment) => attachment.file),
          selectedWorkspaceId,
        );
        uploadedFiles = [
          ...uploadResult.uploaded,
          ...(uploadResult.failed ?? []).map((file) => ({ ...file, status: 'failed' as const })),
        ];
        if (userMsg) get().updateMessage(userMsg.id, { files: uploadedFiles });
        useWorkspaceStore.getState().loadWorkspace(conversationId);
      }

      await streamChat(
        conversationId,
        trimmedContent,
        selectedModelForRequest,
        get().contextProfile.id,
        uploadedFiles,
        ({ event, data }) => {
          if (abort.signal.aborted) return;
          if (event === 'segment_start') {
            const execution = normalizeExecutionSegment({
              ...data,
              status: data.status ?? 'running',
              steps: [],
              errors: [],
            });
            activeExecutionSegmentId = execution.id;
            structuredExecutionActive = true;
            activeTextSegmentId = null;
            activeThinkingSegmentId = null;
            appendSegment({
              id: `execution-${execution.id}`,
              type: 'execution',
              execution,
            });
            return;
          }

          if (event === 'segment_update') {
            const segmentId = String(data.id ?? activeExecutionSegmentId ?? '');
            if (!segmentId) return;
            updateExecutionSegment(segmentId, (segment) => ({
              ...segment,
              ...normalizeExecutionSegment({ ...segment, ...data, steps: segment.steps, errors: segment.errors }),
            }));
            return;
          }

          if (event === 'segment_end') {
            const segmentId = String(data.id ?? activeExecutionSegmentId ?? '');
            if (!segmentId) return;
            updateExecutionSegment(segmentId, (segment) => ({
              ...segment,
              status: executionStatus(data.status ?? 'completed'),
              endedAt: data.endedAt ? String(data.endedAt) : segment.endedAt,
              durationMs: optionalNumber(data.durationMs) ?? segment.durationMs,
              thinkingCount: numberCount(data.thinkingCount ?? segment.thinkingCount),
              toolCallCount: numberCount(data.toolCallCount ?? segment.toolCallCount),
              commandCount: numberCount(data.commandCount ?? segment.commandCount),
              fileReadCount: numberCount(data.fileReadCount ?? segment.fileReadCount),
              fileWriteCount: numberCount(data.fileWriteCount ?? segment.fileWriteCount),
              fileEditCount: numberCount(data.fileEditCount ?? segment.fileEditCount),
              webRequestCount: numberCount(data.webRequestCount ?? segment.webRequestCount),
              recallCount: numberCount(data.recallCount ?? segment.recallCount),
              errorCount: numberCount(data.errorCount ?? segment.errorCount),
              totalTokens: optionalNumber(data.totalTokens) ?? segment.totalTokens,
              defaultCollapsed: true,
            }));
            if (activeExecutionSegmentId === segmentId) activeExecutionSegmentId = null;
            structuredExecutionActive = false;
            return;
          }

          if (event === 'step_start') {
            const segmentId = String(data.segmentId ?? activeExecutionSegmentId ?? '');
            if (!segmentId) return;
            upsertExecutionStep(segmentId, normalizeExecutionStep(data, segmentId));
            return;
          }

          if (event === 'step_delta') {
            const segmentId = String(data.segmentId ?? activeExecutionSegmentId ?? '');
            const stepId = String(data.stepId ?? data.id ?? '');
            if (!segmentId || !stepId) return;
            const delta = String(data.delta ?? data.content ?? '');
            updateExecutionSegment(segmentId, (segment) => ({
              ...segment,
              steps: segment.steps.map((step) =>
                step.id === stepId
                  ? { ...step, content: `${step.content ?? ''}${delta}` }
                  : step,
              ),
            }));
            return;
          }

          if (event === 'step_end') {
            const segmentId = String(data.segmentId ?? activeExecutionSegmentId ?? '');
            const stepId = String(data.stepId ?? data.id ?? '');
            if (!segmentId || !stepId) return;
            updateExecutionSegment(segmentId, (segment) => ({
              ...segment,
              steps: segment.steps.map((step) =>
                step.id === stepId
                  ? {
                      ...step,
                      status: executionStepStatus(data.status ?? 'completed'),
                      endedAt: data.endedAt ? String(data.endedAt) : step.endedAt,
                      durationMs: optionalNumber(data.durationMs) ?? step.durationMs,
                      outputPreview: data.outputPreview ? String(data.outputPreview) : step.outputPreview,
                      error: data.error ? String(data.error) : step.error,
                      metadata:
                        data.metadata && typeof data.metadata === 'object'
                          ? (data.metadata as Record<string, unknown>)
                          : step.metadata,
                      defaultCollapsed: true,
                    }
                  : step,
              ),
            }));
            return;
          }

          if (event === 'workflow_error') {
            const segmentId = String(data.segmentId ?? activeExecutionSegmentId ?? '');
            const error = normalizeWorkflowError(data, segmentId || undefined);
            if (segmentId) appendWorkflowError(segmentId, error);
            appendMessageWorkflowError(data, {
              title: error.title,
              message: error.message,
              errorType: error.errorType,
              severity: error.severity,
            });
            set({ apiError: `${error.title}: ${error.message}` });
            shouldAutoResumeWorkflow = error.recoverable;
            return;
          }

          if (event === 'artifact_open') {
            const artifact = normalizeArtifactRef(data, selectedWorkspaceId);
            if (artifact.path) {
              appendSegment({ id: `artifact-${artifact.id}`, type: 'artifact', artifact });
              void useWorkbenchStore.getState().openFile(
                artifact.workspaceId ?? selectedWorkspaceId,
                artifact.path,
              );
            }
            return;
          }

          if (event === 'thinking_start') {
            if (structuredExecutionActive || activeExecutionSegmentId) return;
            activeThinkingSegmentId = generateId();
            activeTextSegmentId = null;
            appendSegment({
              id: activeThinkingSegmentId,
              type: 'thinking',
              content: '',
              summary: '思考中...',
              status: 'streaming',
            });
            return;
          }

          if (event === 'thinking_delta') {
            if (structuredExecutionActive || activeExecutionSegmentId) return;
            const delta = String(data.content ?? '');
            if (!activeThinkingSegmentId) {
              activeThinkingSegmentId = generateId();
              appendSegment({
                id: activeThinkingSegmentId,
                type: 'thinking',
                content: '',
                summary: '思考中...',
                status: 'streaming',
              });
            }
            updateSegments(activeThinkingSegmentId, (segment) => {
              if (segment.type !== 'thinking') return segment;
              return { ...segment, content: `${segment.content}${delta}` };
            });
            return;
          }

          if (event === 'thinking_end') {
            if (structuredExecutionActive || activeExecutionSegmentId) return;
            const current = get().messages.find((m) => m.id === currentMsgId);
            const finishedId = activeThinkingSegmentId;
            const finished = current?.segments?.find(
              (segment) => segment.id === finishedId && segment.type === 'thinking',
            );
            if (finishedId && finished?.type === 'thinking') {
              const rawThinking = finished.content.trim();
              const fallbackSummary = compactPhrase(rawThinking);
              updateSegments(finishedId, (segment) =>
                segment.type === 'thinking'
                  ? { ...segment, summary: fallbackSummary, status: 'complete' }
                  : segment,
              );
              if (rawThinking) {
                void summarizeThinking(rawThinking.slice(0, 4000), selectedModelForRequest)
                  .then((summary) => {
                    if (!summary.trim()) return;
                    updateSegments(finishedId, (segment) =>
                      segment.type === 'thinking'
                        ? { ...segment, summary: summary.trim().slice(0, 32) }
                        : segment,
                    );
                  })
                  .catch(() => {});
              }
            }
            activeThinkingSegmentId = null;
            activeTextSegmentId = null;
            return;
          }

          if (event === 'text_delta' || event === 'markdown_delta') {
            const delta = String(data.content ?? '');
            const current = get().messages.find((m) => m.id === currentMsgId);
            if (!activeTextSegmentId) {
              activeTextSegmentId = generateId();
              appendSegment({ id: activeTextSegmentId, type: 'text', content: '' });
            }
            updateSegments(activeTextSegmentId, (segment) =>
              segment.type === 'text'
                ? { ...segment, content: `${segment.content}${delta}` }
                : segment,
            );
            get().updateMessage(currentMsgId, {
              content: `${current?.content ?? ''}${delta}`,
            });
            return;
          }

          if (event === 'tool_call_start') {
            if (structuredExecutionActive || activeExecutionSegmentId) return;
            const callId = String(data.call_id ?? '');
            const toolName = String(data.tool ?? '');
            if (isInteractiveToolName(toolName)) {
              return;
            }
            const args =
              data.arguments && typeof data.arguments === 'object'
                ? (data.arguments as Record<string, unknown>)
                : {};
            const newCall: ToolCall = {
              id: callId,
              name: toolName,
              arguments: args,
              status: 'running',
              startTime: Date.now(),
            };
            activeTextSegmentId = null;
            activeThinkingSegmentId = null;
            const current = get().messages.find((m) => m.id === currentMsgId);
            const existing = current?.toolCalls ?? [];
            get().updateMessage(currentMsgId, {
              type: 'tool_call',
              toolCalls: [...existing, newCall],
              segments: [
                ...(current?.segments ?? []),
                { id: `tool-${callId || generateId()}`, type: 'tool', tool: newCall },
              ],
            });
            return;
          }

          if (event === 'interaction_required') {
            const pending = normalizePendingInteraction(data);
            if (pending) set({ pendingInteraction: pending });
            return;
          }

          if (event === 'agent_paused') {
            // Mark the message as waiting for user
            const current = get().messages.find((m) => m.id === currentMsgId);
            if (current?.interaction) {
              get().updateMessage(currentMsgId, {
                interaction: { ...current.interaction, resolved: false },
              });
            }
            return;
          }

          if (event === 'agent_resumed') {
            set({ pendingInteraction: null });
            return;
          }

          if (event === 'tool_result') {
            if (structuredExecutionActive || activeExecutionSegmentId) return;
            const callId = String(data.call_id ?? '');
            const toolName = String(data.tool ?? '');
            const success = Boolean(data.success);
            const result = data.result ?? null;
            if (success && isInteractiveToolName(toolName) && result && typeof result === 'object') {
              const pending = normalizePendingInteraction(result as Record<string, unknown>, callId);
              if (pending) {
                set({ pendingInteraction: pending });
              }
              return;
            }
            const error = data.error ? String(data.error) : undefined;
            const duration = Number(data.duration_ms ?? 0);
            const current = get().messages.find((m) => m.id === currentMsgId);
            const toolCalls = (current?.toolCalls ?? []).map((tc) =>
              tc.id === callId
                ? {
                    ...tc,
                    status: success ? ('success' as const) : ('error' as const),
                    result,
                    error,
                    duration,
                  }
                : tc,
            );
            const updatedTool = toolCalls.find((tc) => tc.id === callId);

            // Detect todo list updates from tool results
            const updates: Partial<Message> = {
              toolCalls,
              segments: (current?.segments ?? []).map((segment) =>
                segment.type === 'tool' && segment.tool.id === callId && updatedTool
                  ? { ...segment, tool: updatedTool }
                  : segment,
              ),
            };

            if (result && typeof result === 'object' && (result as any).items) {
              const todoResult = result as { items: any[]; count: number };
              updates.todo = {
                items: todoResult.items.map((it: any) => ({
                  id: it.id || '',
                  title: it.title || '',
                  status: (it.status || 'todo') as any,
                  note: it.note,
                })),
                count: todoResult.count,
              };
            }

            get().updateMessage(currentMsgId, updates);
            return;
          }

          if (event === 'error') {
            const detail = String(data.detail ?? 'Unknown API error');
            const errorCode = String(data.code ?? 'stream_error');
            console.error('Chat stream returned error event', data);
            const current = get().messages.find((m) => m.id === currentMsgId);
            const errorSegment = createWorkflowErrorSegment(data, {
              title: '工作流已中断',
              message: detail,
              errorType: errorCode,
              severity: 'error',
            });
            get().updateMessage(currentMsgId, {
              content: detail,
              type: 'error',
              status: 'error',
              segments: [
                ...(current?.segments ?? []),
                errorSegment,
              ],
            });
            set({ apiError: detail, isStreaming: false });
            shouldAutoResumeWorkflow = errorCode !== 'CONTEXT_LIMIT_EXCEEDED';
            return;
          }

          if (event === 'aborted') {
            const current = get().messages.find((m) => m.id === currentMsgId);
            const reason = String(data.reason ?? 'user_request');
            get().updateMessage(currentMsgId, {
              status: 'error',
              content: 'Generation stopped.',
              segments: [
                ...(current?.segments ?? []),
                createWorkflowErrorSegment(data, {
                  title: '工作流已停止',
                  message: reason === 'user_request' ? '用户主动停止了生成。' : `生成已停止：${reason}`,
                  errorType: 'aborted',
                  severity: 'warning',
                }),
              ],
            });
            set({ isStreaming: false });
            return;
          }

          if (event === 'context_usage') {
            const inputTokens = Number(data.input_tokens ?? 0);
            const outputTokens = Number(data.output_tokens ?? 0);
            set((state) => {
              if (!state.contextUsage) return state;
              return {
                contextUsage: {
                  ...state.contextUsage,
                  totalTokens: inputTokens + outputTokens,
                },
              };
            });
            return;
          }

          if (event === 'context_status') {
            useContextToastStore.getState().pushContextToast(data);
            return;
          }

          if (event === 'message_end') {
            get().updateMessage(currentMsgId, { status: 'complete' });
            set({ isStreaming: false });
          }
        },
        abort.signal,
        {
          internalContinue,
          workspaceId: selectedWorkspaceId,
          permissionMode: sessionDraft.permissionMode,
          directoryAccessMode: sessionDraft.directoryAccessMode,
          references: referenceList.map((ref) => ({
            sourceType: ref.sourceType,
            sourceId: ref.sourceId,
            title: ref.title,
            preview: ref.preview,
            instruction: ref.instruction,
            location: ref.location,
            payload: ref.payload,
          })),
        },
      );

      const latest = get().messages.find((m) => m.id === currentMsgId);
      if (latest?.status === 'streaming') {
        get().updateMessage(currentMsgId, { status: 'complete' });
      }
      // Refresh context usage after streaming completes
      void get().fetchContextUsage();
      const finalAssistant = get().messages.find((m) => m.id === currentMsgId);
      const turnCount = get().messages.filter((message) => message.role === 'user').length;
      if (!internalContinue && finalAssistant?.status === 'complete' && turnCount > 0 && turnCount <= 2) {
        void summarizeConversationTitle(conversationId, selectedModelForRequest)
          .then((title) => {
            if (!title.trim()) return;
            set((state) => ({
              conversations: state.conversations.map((conversation) =>
                conversation.id === conversationId
                  ? { ...conversation, title: title.trim(), updatedAt: Date.now() }
                  : conversation,
              ),
            }));
          })
          .catch(() => {});
      }
      // Completed successfully; attachments/references were already hidden from
      // the composer when the user sent the message.
    } catch (error) {
      // AbortError is expected on user-triggered stop — not a real error
      if (error instanceof DOMException && error.name === 'AbortError') {
        get().updateMessage(currentMsgId, {
          status: 'complete',
          content: get().messages.find((m) => m.id === currentMsgId)?.content || '',
        });
      } else {
        const detail = error instanceof Error ? error.message : String(error);
        console.error('Chat stream failed', error);
        const current = get().messages.find((m) => m.id === currentMsgId);
        get().updateMessage(currentMsgId, {
          content: detail,
          type: 'error',
          status: 'error',
          segments: [
            ...(current?.segments ?? []),
            createWorkflowErrorSegment(error, {
              title: '工作流异常中断',
              message: detail,
              errorType: 'client_stream_error',
              severity: 'error',
            }),
          ],
        });
        set({ apiError: detail });
        shouldAutoResumeWorkflow = true;
      }
    } finally {
      set((state) => ({
        isStreaming: false,
        _abortController: null,
        attachments: state.attachments.map((attachment) => ({ ...attachment, uploading: false })),
      }));
      if (
        shouldAutoResumeWorkflow &&
        !abort.signal.aborted &&
        (options.autoResumeDepth ?? 0) < MAX_WORKFLOW_AUTO_RESUMES
      ) {
        window.setTimeout(() => {
          if (get().isStreaming || get().currentConversationId !== conversationId) return;
          void get().sendMessage(WORKFLOW_AUTO_RESUME_PROMPT, {
            internalContinue: true,
            autoResumeDepth: (options.autoResumeDepth ?? 0) + 1,
          });
        }, 250);
      }
    }
  },

  resumeWorkflow: async (prompt) => {
    await get().sendMessage(prompt || WORKFLOW_AUTO_RESUME_PROMPT, {
      internalContinue: true,
      autoResumeDepth: 0,
    });
  },

  stopGeneration: () => {
    const ctrl = get()._abortController;
    if (ctrl) {
      ctrl.abort();
      set({ _abortController: null });
    }
    const conversationId = get().currentConversationId;
    if (conversationId) {
      stopChat(conversationId).catch(() => {});
    }
  },

  respondToInteraction: async (choice, message) => {
    const conversationId = get().currentConversationId;
    const pending = get().pendingInteraction;
    if (!conversationId || !pending) return;

    const interactionId = pending.interactionId || pending.toolCallId;
    try {
      const response = await fetch(`/api/agent-runs/${conversationId}/interactions/${interactionId}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ choice, message: message || null }),
      });
      if (!response.ok) {
        const detail = await response.text().catch(() => '');
        throw new Error(detail || `Failed to submit interaction: HTTP ${response.status}`);
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      console.error('Interaction response failed', error);
      get().addMessage(
        projectErrorMessage(error, {
          title: '交互响应提交失败',
          message: detail,
          errorType: 'interaction_response_error',
          severity: 'error',
        }),
      );
      set({ apiError: detail });
      throw error;
    }
  },

  selectConversation: async (id) => {
    const conversation = get().conversations.find((c) => c.id === id);
    if (!conversation) return;

    set({ currentConversationId: id, pendingInteraction: null });

    try {
      const result = await getConversationMessages(id);
      const messages: Message[] = result.messages.map((m) => {
        const role = m.role as 'user' | 'assistant';
        const segments =
          role === 'assistant'
            ? normalizeAssistantSegments(m.segments, m.thinking, m.content)
            : [];
        const segmentToolCalls = segments
          .filter((segment): segment is Extract<MessageSegment, { type: 'tool' }> =>
            segment.type === 'tool',
          )
          .map((segment) => segment.tool);
        const persistedToolCalls = Array.isArray(m.tool_calls)
          ? m.tool_calls.map((tool) => normalizeToolCall(tool))
          : [];
        const toolCalls = segmentToolCalls.length ? segmentToolCalls : persistedToolCalls;
        return {
          id: generateId(),
          role,
          content: m.content,
          thinkingContent: m.thinking ?? undefined,
          segments: segments.length ? segments : undefined,
          toolCalls: toolCalls.length ? toolCalls : undefined,
          files: m.files ?? undefined,
          type: 'text',
          timestamp: Date.parse(m.timestamp) || Date.now(),
          status: 'complete' as const,
        };
      });
      set({ messages });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      set({
        messages: [
          projectErrorMessage(error, {
            title: '加载对话失败',
            message: detail,
            errorType: 'conversation_load_error',
            severity: 'error',
          }),
        ],
        apiError: detail,
      });
    }

    // Load workspace file tree for this conversation. Project conversations share project workspace.
    useWorkspaceStore.getState().loadWorkspace(String(conversation.metadata?.workspace_id || id));
    // Refresh context usage for the selected conversation
    void get().fetchContextUsage();
  },

  createConversation: async (title = 'New chat') => {
    const projectId = useSessionDraftStore.getState().workspaceId;
    const projectConversation = projectId
      ? get().conversations.find((conversation) => conversation.metadata?.project_id === projectId)
      : undefined;
    const projectName = projectId
      ? projectConversation?.metadata?.project_name || projectId
      : undefined;
    const workspaceId = projectId
      ? projectConversation?.metadata?.workspace_id || projectId
      : undefined;
    const metadata = projectId
      ? { project_id: projectId, project_name: String(projectName), workspace_id: String(workspaceId) }
      : {};
    const conversation = await apiCreateConversation(title, get().selectedModelId, metadata);
    set((state) => ({
      conversations: [conversation, ...state.conversations],
      currentConversationId: conversation.id,
      messages: [],
      contextUsage: null,
      apiError: null,
      pendingInteraction: null,
    }));
    // Load workspace for the new conversation (will be empty initially)
    useWorkspaceStore.getState().loadWorkspace(String(conversation.metadata?.workspace_id || conversation.id));
    return conversation.id;
  },

  createProject: async ({ name, directoryPath }) => {
    const { project, firstConversation } = await apiCreateProject({
      name,
      directoryPath,
      model: get().selectedModelId,
      firstConversationTitle: '新对话',
    });
    useSessionDraftStore.getState().setWorkspaceId(project.id);
    set((state) => ({
      conversations: [firstConversation, ...state.conversations],
      currentConversationId: firstConversation.id,
      messages: [],
      contextUsage: null,
      apiError: null,
      pendingInteraction: null,
    }));
    useWorkspaceStore.getState().loadWorkspace(project.workspaceId || project.id);
    void useWorkspaceStore.getState().loadWorkspaceList();
    return project.id;
  },

  deleteConversation: async (id) => {
    await apiDeleteConversation(id);
    set((state) => {
      const conversations = state.conversations.filter((c) => c.id !== id);
      if (state.currentConversationId === id) {
        const first = conversations[0];
        const newId = first?.id ?? null;
        if (newId) {
          const nextConversation = conversations.find((conversation) => conversation.id === newId);
          useWorkspaceStore.getState().loadWorkspace(String(nextConversation?.metadata?.workspace_id || newId));
        }
        else useWorkspaceStore.getState().loadWorkspace(null);
        return {
          conversations,
          currentConversationId: newId,
          messages: first?.messages ?? [],
          pendingInteraction: null,
        };
      }
      return { conversations };
    });
  },

  renameProject: async (projectId, name) => {
    const project = await apiRenameProject(projectId, name);
    set((state) => ({
      conversations: state.conversations.map((conversation) =>
        conversation.metadata?.project_id === projectId
          ? {
              ...conversation,
              metadata: {
                ...(conversation.metadata ?? {}),
                project_id: projectId,
                project_name: project.name,
              },
            }
          : conversation,
      ),
    }));
  },

  deleteProject: async (projectId) => {
    await apiDeleteProject(projectId);
    set((state) => {
      const conversations = state.conversations.filter(
        (conversation) => conversation.metadata?.project_id !== projectId,
      );
      const currentStillExists = conversations.some((conversation) => conversation.id === state.currentConversationId);
      const next = currentStillExists ? state.currentConversationId : null;
      if (next) {
        const nextConversation = conversations.find((conversation) => conversation.id === next);
        useWorkspaceStore.getState().loadWorkspace(String(nextConversation?.metadata?.workspace_id || next));
      }
      else useWorkspaceStore.getState().loadWorkspace(null);
      return {
        conversations,
        currentConversationId: next,
        messages: currentStillExists ? state.messages : [],
        pendingInteraction: null,
      };
    });
  },

  clearAll: async () => {
    await apiDeleteAllConversations();
    useWorkspaceStore.getState().loadWorkspace(null);
    set({
      conversations: [],
      currentConversationId: null,
      messages: [],
      contextUsage: null,
      pendingInteraction: null,
      apiError: null,
    });
  },

  setSelectedModel: (id) => set({ selectedModelId: id }),
  setContextProfile: (profile) => set({ contextProfile: profile }),

  switchContextProfile: (profileId) => {
    const profile = get().availableProfiles.find((p) => p.id === profileId);
    if (profile) {
      set({ contextProfile: profile });
    }
  },

  fetchContextUsage: async () => {
    const conversationId = get().currentConversationId;
    if (!conversationId) return;
    try {
      const modelId = get().selectedModelId;
      const profile = get().contextProfile.id;
      const data = await getContextUsage(conversationId, modelId, profile);
      const usage: ContextUsage = {
        conversationId: data.conversation_id,
        totalTokens: data.total_tokens,
        maxTokens: data.max_tokens,
        availableBudget: data.available_budget,
        outputReserved: data.output_reserved,
        safetyMargin: data.safety_margin,
        profile: data.profile,
        model: data.model,
        usageRatio: data.usage_ratio,
        compressionLevel: data.compression_level,
        budgetHealthy: data.budget_healthy,
        components: data.components,
        messageCount: data.message_count,
        userMessageCount: data.user_message_count,
        toolCallCount: data.tool_call_count,
        workspaceFileCount: data.workspace_file_count,
        memoryItemCount: data.memory_item_count,
      };
      set({ contextUsage: usage });
    } catch {
      // Silently fail — context usage is non-critical UI
    }
  },

  setIsStreaming: (v) => set({ isStreaming: v }),

  addAttachment: (file) =>
    set((state) => {
      const error = validateAttachment(file, state.attachments);
      if (error) {
        return { apiError: error };
      }
      return {
        attachments: [...state.attachments, { id: generateId(), file, uploading: false }],
        apiError: null,
      };
    }),

  removeAttachment: (id) =>
    set((state) => ({
      attachments: state.attachments.filter((a) => a.id !== id),
    })),

  clearAttachments: () => set({ attachments: [] }),
  setSuggestions: (suggestions) => set({ suggestions }),
  clearApiError: () => set({ apiError: null }),
  clearMessages: () => set({ messages: [] }),
}));
