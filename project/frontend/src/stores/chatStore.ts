import { create } from 'zustand';
import type { Message, Conversation, Model, ContextProfile, ToolCall } from '@/types';
import { mockContextProfile, contextProfiles } from '@/services/mockData';
import {
  createConversation as apiCreateConversation,
  deleteConversation as apiDeleteConversation,
  listConversations,
  listModels,
  streamChat,
  stopChat,
  getConversationMessages,
} from '@/services/api';
import { generateId } from '@/lib/utils';
import { useWorkspaceStore } from './workspaceStore';

interface ChatState {
  conversations: Conversation[];
  currentConversationId: string | null;
  messages: Message[];
  models: Model[];
  selectedModelId: string;
  contextProfile: ContextProfile;
  availableProfiles: ContextProfile[];
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
  selectConversation: (id: string) => Promise<void>;
  createConversation: (title?: string) => Promise<string>;
  deleteConversation: (id: string) => Promise<void>;
  setSelectedModel: (id: string) => void;
  setContextProfile: (profile: ContextProfile) => void;
  switchContextProfile: (profileId: string) => void;
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

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  currentConversationId: null,
  messages: [],
  models: fallbackModels,
  selectedModelId: fallbackModels[0].id,
  contextProfile: mockContextProfile,
  availableProfiles: contextProfiles,
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

    // Single assistant message accumulates all rounds (think + text + tools).
    const currentMsgId = assistantMsg.id;

    try {
      await streamChat(
        conversationId,
        content,
        get().selectedModelId,
        ({ event, data }) => {
          if (abort.signal.aborted) return;
          if (event === 'thinking_start') {
            // Push previous block, start fresh one (all in the same bubble)
            const current = get().messages.find((m) => m.id === currentMsgId);
            const curContent = current?.thinkingContent || '';
            const blocks = [...(current?.thinkingBlocks || [])];
            if (curContent.trim()) {
              blocks.push(curContent);
            }
            get().updateMessage(currentMsgId, {
              thinkingContent: '',
              thinkingBlocks: blocks,
            });
            return;
          }

          if (event === 'thinking_delta') {
            const delta = String(data.content ?? '');
            const current = get().messages.find((m) => m.id === currentMsgId);
            get().updateMessage(currentMsgId, {
              thinkingContent: `${current?.thinkingContent ?? ''}${delta}`,
            });
            return;
          }

          if (event === 'thinking_end') {
            const current = get().messages.find((m) => m.id === currentMsgId);
            const curContent = current?.thinkingContent || '';
            const blocks = [...(current?.thinkingBlocks || [])];
            if (curContent.trim()) {
              blocks.push(curContent);
            }
            get().updateMessage(currentMsgId, {
              thinkingContent: '',
              thinkingBlocks: blocks,
            });
            return;
          }

          if (event === 'text_delta' || event === 'markdown_delta') {
            const delta = String(data.content ?? '');
            const current = get().messages.find((m) => m.id === currentMsgId);
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
            const current = get().messages.find((m) => m.id === currentMsgId);
            const existing = current?.toolCalls ?? [];
            get().updateMessage(currentMsgId, {
              type: 'tool_call',
              toolCalls: [...existing, newCall],
            });
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
            get().updateMessage(currentMsgId, { toolCalls });
            return;
          }

          if (event === 'error') {
            const detail = String(data.detail ?? 'Unknown API error');
            get().updateMessage(currentMsgId, {
              content: detail,
              type: 'error',
              status: 'error',
            });
            set({ apiError: detail, isStreaming: false });
            return;
          }

          if (event === 'aborted') {
            get().updateMessage(currentMsgId, {
              status: 'error',
              content: 'Generation stopped.',
            });
            set({ isStreaming: false });
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
    } catch (error) {
      // AbortError is expected on user-triggered stop — not a real error
      if (error instanceof DOMException && error.name === 'AbortError') {
        get().updateMessage(currentMsgId, {
          status: 'complete',
          content: get().messages.find((m) => m.id === currentMsgId)?.content || '',
        });
      } else {
        const detail = error instanceof Error ? error.message : String(error);
        get().updateMessage(currentMsgId, {
          content: detail,
          type: 'error',
          status: 'error',
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
    // Also notify backend
    const conversationId = get().currentConversationId;
    if (conversationId) {
      stopChat(conversationId).catch(() => {});
    }
  },

  selectConversation: async (id) => {
    const conversation = get().conversations.find((c) => c.id === id);
    if (!conversation) return;

    set({ currentConversationId: id });

    try {
      const result = await getConversationMessages(id);
      const messages: Message[] = result.messages.map((m) => ({
        id: generateId(),
        role: m.role as 'user' | 'assistant',
        content: m.content,
        thinkingContent: m.thinking ?? undefined,
        type: m.role === 'user' ? 'text' : 'text',
        timestamp: Date.parse(m.timestamp) || Date.now(),
        status: 'complete' as const,
      }));
      set({ messages });
    } catch {
      set({ messages: [] });
    }

    // Load workspace file tree for this conversation
    useWorkspaceStore.getState().loadWorkspace(id);
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
