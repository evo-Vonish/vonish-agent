import { create } from 'zustand';
import type {
  Message,
  Conversation,
  Model,
  ContextProfile,
  ContextUsage,
  ToolCall,
  MessageSegment,
} from '@/types';
import { mockContextProfile, contextProfiles } from '@/services/mockData';
import {
  createConversation as apiCreateConversation,
  deleteConversation as apiDeleteConversation,
  listConversations,
  listModels,
  streamChat,
  stopChat,
  getConversationMessages,
  summarizeConversationTitle,
  summarizeThinking,
  getContextUsage,
} from '@/services/api';
import { generateId } from '@/lib/utils';
import { useWorkspaceStore } from './workspaceStore';
import { useToolStore } from './useToolStore';

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

  initialize: () => Promise<void>;
  setInputText: (text: string) => void;
  addMessage: (msg: Message) => void;
  updateMessage: (id: string, partial: Partial<Message>) => void;
  sendMessage: (content: string) => Promise<void>;
  stopGeneration: () => void;
  respondToInteraction: (choice: string, message?: string) => Promise<void>;
  selectConversation: (id: string) => Promise<void>;
  createConversation: (title?: string) => Promise<string>;
  deleteConversation: (id: string) => Promise<void>;
  setSelectedModel: (id: string) => void;
  setContextProfile: (profile: ContextProfile) => void;
  switchContextProfile: (profileId: string) => void;
  fetchContextUsage: () => Promise<void>;
  setIsStreaming: (v: boolean) => void;
  addAttachment: (file: File) => void;
  removeAttachment: (id: string) => void;
  clearAttachments: () => void;
  setSuggestions: (suggestions: string[]) => void;
  clearMessages: () => void;
}

const fallbackModels: Model[] = [
  {
    id: 'deepseek-v4-flash',
    name: 'DeepSeek V4 Flash',
    provider: 'deepseek',
    description: 'Fast DeepSeek chat model',
    maxTokens: 8192,
    contextWindow: 1_000_000,
    tags: ['chat'],
  },
  {
    id: 'deepseek-v4-pro',
    name: 'DeepSeek V4 Pro',
    provider: 'deepseek',
    description: 'DeepSeek reasoning model',
    maxTokens: 8192,
    contextWindow: 1_000_000,
    tags: ['thinking'],
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

function updateSegment(
  segments: MessageSegment[] | undefined,
  segmentId: string,
  updater: (segment: MessageSegment) => MessageSegment,
): MessageSegment[] {
  return (segments ?? []).map((segment) =>
    segment.id === segmentId ? updater(segment) : segment,
  );
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  currentConversationId: null,
  messages: [],
  models: fallbackModels,
  selectedModelId: fallbackModels[0].id,
  contextProfile: mockContextProfile,
  availableProfiles: contextProfiles,
  contextUsage: null,
  isStreaming: false,
  inputText: '',
  attachments: [],
  suggestions: [],
  apiError: null,
  initialized: false,
  _abortController: null,

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
          messages: currentConversation?.messages ?? [],
          initialized: true,
          apiError: null,
        };
      });
      // Load workspace for initial conversation
      const cid = get().currentConversationId;
      if (cid) useWorkspaceStore.getState().loadWorkspace(cid);
      // Load tools from backend
      void useToolStore.getState().loadToolsFromBackend();
    } catch (error) {
      set({
        initialized: true,
        apiError: error instanceof Error ? error.message : String(error),
      });
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

  sendMessage: async (content) => {
    if (get().isStreaming) return;

    let conversationId = get().currentConversationId;
    if (!conversationId) {
      conversationId = await get().createConversation(firstLineTitle(content));
    }

    const userMsg: Message = {
      id: generateId(),
      role: 'user',
      content,
      type: 'text',
      timestamp: Date.now(),
      status: 'complete',
    };
    get().addMessage(userMsg);

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
    set({ isStreaming: true, apiError: null, _abortController: abort });

    const currentMsgId = assistantMsg.id;
    const selectedModelForRequest = get().selectedModelId;
    let activeThinkingSegmentId: string | null = null;
    let activeTextSegmentId: string | null = null;

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

    try {
      await streamChat(
        conversationId,
        content,
        selectedModelForRequest,
        ({ event, data }) => {
          if (abort.signal.aborted) return;
          if (event === 'thinking_start') {
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
            const callId = String(data.call_id ?? '');
            const toolName = String(data.tool ?? '');
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
            const payload = data as any;
            const current = get().messages.find((m) => m.id === currentMsgId);
            get().updateMessage(currentMsgId, {
              type: 'interaction',
              interaction: {
                interaction_id: String(payload.interaction_id ?? ''),
                type: String(payload.type ?? '') as 'ask_user_question' | 'request_approval',
                title: String(payload.title ?? ''),
                description: payload.description ? String(payload.description) : undefined,
                options: Array.isArray(payload.options) ? payload.options : [],
                plan: Array.isArray(payload.payload?.plan) ? payload.payload.plan : undefined,
                allow_custom_response: payload.payload?.allow_custom_response ?? true,
                risk_level: payload.payload?.risk_level ?? 'medium',
              },
            });
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
            const choice = String(data.choice ?? '');
            const message = data.message ? String(data.message) : undefined;
            const current = get().messages.find((m) => m.id === currentMsgId);
            if (current?.interaction) {
              get().updateMessage(currentMsgId, {
                interaction: {
                  ...current.interaction,
                  resolved: true,
                  response: { choice, message },
                },
              });
            }
            return;
          }

          if (event === 'tool_result') {
            const callId = String(data.call_id ?? '');
            const success = Boolean(data.success);
            const result = data.result ?? null;
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
            const current = get().messages.find((m) => m.id === currentMsgId);
            get().updateMessage(currentMsgId, {
              content: detail,
              type: 'error',
              status: 'error',
              segments: [
                ...(current?.segments ?? []),
                { id: generateId(), type: 'text', content: detail },
              ],
            });
            set({ apiError: detail, isStreaming: false });
            return;
          }

          if (event === 'aborted') {
            const current = get().messages.find((m) => m.id === currentMsgId);
            get().updateMessage(currentMsgId, {
              status: 'error',
              content: 'Generation stopped.',
              segments: [
                ...(current?.segments ?? []),
                { id: generateId(), type: 'text', content: 'Generation stopped.' },
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

          if (event === 'message_end') {
            get().updateMessage(currentMsgId, { status: 'complete' });
            set({ isStreaming: false });
          }
        },
        abort.signal,
      );

      const latest = get().messages.find((m) => m.id === currentMsgId);
      if (latest?.status === 'streaming') {
        get().updateMessage(currentMsgId, { status: 'complete' });
      }
      // Refresh context usage after streaming completes
      void get().fetchContextUsage();
      const finalAssistant = get().messages.find((m) => m.id === currentMsgId);
      const turnCount = get().messages.filter((message) => message.role === 'user').length;
      if (finalAssistant?.status === 'complete' && turnCount > 0 && turnCount <= 2) {
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
    } catch (error) {
      // AbortError is expected on user-triggered stop — not a real error
      if (error instanceof DOMException && error.name === 'AbortError') {
        get().updateMessage(currentMsgId, {
          status: 'complete',
          content: get().messages.find((m) => m.id === currentMsgId)?.content || '',
        });
      } else {
        const detail = error instanceof Error ? error.message : String(error);
        const current = get().messages.find((m) => m.id === currentMsgId);
        get().updateMessage(currentMsgId, {
          content: detail,
          type: 'error',
          status: 'error',
          segments: [
            ...(current?.segments ?? []),
            { id: generateId(), type: 'text', content: detail },
          ],
        });
        set({ apiError: detail });
      }
    } finally {
      set({ isStreaming: false, _abortController: null });
    }
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
    const lastMsg = get().messages.filter(m => m.role === 'assistant' && m.interaction).pop();
    if (!conversationId || !lastMsg?.interaction) return;

    const interactionId = lastMsg.interaction.interaction_id;
    await fetch(`/api/agent-runs/${conversationId}/interactions/${interactionId}/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ choice, message: message || null }),
    });
  },

  selectConversation: async (id) => {
    const conversation = get().conversations.find((c) => c.id === id);
    if (!conversation) return;

    set({ currentConversationId: id });

    try {
      const result = await getConversationMessages(id);
      const messages: Message[] = result.messages.map((m) => {
        const role = m.role as 'user' | 'assistant';
        const segments: MessageSegment[] =
          role === 'assistant'
            ? [
                ...(m.thinking
                  ? [
                      {
                        id: generateId(),
                        type: 'thinking' as const,
                        content: m.thinking,
                        summary: compactPhrase(m.thinking),
                        status: 'complete' as const,
                      },
                    ]
                  : []),
                ...(m.content
                  ? [{ id: generateId(), type: 'text' as const, content: m.content }]
                  : []),
              ]
            : [];
        return {
          id: generateId(),
          role,
          content: m.content,
          thinkingContent: m.thinking ?? undefined,
          segments: segments.length ? segments : undefined,
          type: 'text',
          timestamp: Date.parse(m.timestamp) || Date.now(),
          status: 'complete' as const,
        };
      });
      set({ messages });
    } catch {
      set({ messages: [] });
    }

    // Load workspace file tree for this conversation
    useWorkspaceStore.getState().loadWorkspace(id);
    // Refresh context usage for the selected conversation
    void get().fetchContextUsage();
  },

  createConversation: async (title = 'New chat') => {
    const conversation = await apiCreateConversation(title, get().selectedModelId);
    set((state) => ({
      conversations: [conversation, ...state.conversations],
      currentConversationId: conversation.id,
      messages: [],
      apiError: null,
    }));
    // Load workspace for the new conversation (will be empty initially)
    useWorkspaceStore.getState().loadWorkspace(conversation.id);
    return conversation.id;
  },

  deleteConversation: async (id) => {
    await apiDeleteConversation(id);
    set((state) => {
      const conversations = state.conversations.filter((c) => c.id !== id);
      if (state.currentConversationId === id) {
        const first = conversations[0];
        const newId = first?.id ?? null;
        if (newId) useWorkspaceStore.getState().loadWorkspace(newId);
        else useWorkspaceStore.getState().loadWorkspace(null);
        return {
          conversations,
          currentConversationId: newId,
          messages: first?.messages ?? [],
        };
      }
      return { conversations };
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
    set((state) => ({
      attachments: [...state.attachments, { id: generateId(), file, uploading: false }],
    })),

  removeAttachment: (id) =>
    set((state) => ({
      attachments: state.attachments.filter((a) => a.id !== id),
    })),

  clearAttachments: () => set({ attachments: [] }),
  setSuggestions: (suggestions) => set({ suggestions }),
  clearMessages: () => set({ messages: [] }),
}));
