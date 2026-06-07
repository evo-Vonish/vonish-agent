import { create } from 'zustand';

export interface ContextToastPayload {
  phase: string;
  active: boolean;
  mechanism: string;
  summary: string;
  totalTokens: number;
  estimatedLiveTokens?: number;
  maxTokens: number;
  usageRatio: number;
  components: Record<string, number>;
  contextMemory?: {
    active?: boolean;
    tokens?: number;
    preview?: string;
    policy?: string;
    thinking_retention_turns?: number;
  };
  appendedToolResults?: Array<{
    tool: string;
    success: boolean;
    rawChars: number;
    compressed: boolean;
    storedToolResultId?: string;
  }>;
  compressedToolResults?: number;
  messageCount?: number;
  toolCount?: number;
  buildTimeMs?: number;
  timestamp?: string;
}

interface ContextToastState {
  toast: ContextToastPayload | null;
  visible: boolean;
  expanded: boolean;
  pushContextToast: (payload: Record<string, unknown>) => void;
  dismissContextToast: () => void;
  toggleContextToastExpanded: () => void;
}

let hideTimer: ReturnType<typeof setTimeout> | undefined;

const numberValue = (value: unknown, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const normalizePayload = (payload: Record<string, unknown>): ContextToastPayload => {
  const components =
    payload.components && typeof payload.components === 'object'
      ? (payload.components as Record<string, number>)
      : {};
  const contextMemory =
    payload.contextMemory && typeof payload.contextMemory === 'object'
      ? (payload.contextMemory as ContextToastPayload['contextMemory'])
      : {};
  const appendedToolResults = Array.isArray(payload.appendedToolResults)
    ? (payload.appendedToolResults as ContextToastPayload['appendedToolResults'])
    : [];

  return {
    phase: String(payload.phase ?? 'context_built'),
    active: Boolean(payload.active ?? true),
    mechanism: String(payload.mechanism ?? 'Context Memory'),
    summary: String(payload.summary ?? '上下文压缩状态已更新。'),
    totalTokens: numberValue(payload.totalTokens),
    estimatedLiveTokens: numberValue(payload.estimatedLiveTokens),
    maxTokens: numberValue(payload.maxTokens, 256000),
    usageRatio: numberValue(payload.usageRatio),
    components,
    contextMemory,
    appendedToolResults,
    compressedToolResults: numberValue(payload.compressedToolResults),
    messageCount: numberValue(payload.messageCount),
    toolCount: numberValue(payload.toolCount),
    buildTimeMs: numberValue(payload.buildTimeMs),
    timestamp: String(payload.timestamp ?? new Date().toISOString()),
  };
};

export const useContextToastStore = create<ContextToastState>((set, get) => ({
  toast: null,
  visible: false,
  expanded: false,

  pushContextToast: (payload) => {
    if (hideTimer) clearTimeout(hideTimer);
    const normalized = normalizePayload(payload);
    set({ toast: normalized, visible: true });
    hideTimer = setTimeout(() => {
      if (!get().expanded) set({ visible: false });
    }, 7600);
  },

  dismissContextToast: () => {
    if (hideTimer) clearTimeout(hideTimer);
    set({ visible: false, expanded: false });
  },

  toggleContextToastExpanded: () => {
    if (hideTimer) clearTimeout(hideTimer);
    set((state) => ({ expanded: !state.expanded, visible: true }));
  },
}));
