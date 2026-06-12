import { useState, useEffect, useRef, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import {
  Bug,
  ClipboardList,
  Code2,
  FileText,
  FolderTree,
  GitBranch,
  GraduationCap,
  Mic,
  PenLine,
  Plus,
  Presentation,
  Search,
  Send,
  Sparkles,
  Square,
  Terminal,
} from 'lucide-react';
import { ConfigPanel } from '@/components/composer/ConfigPanel';
import { ComposerContextBar } from '@/components/composer/ComposerContextBar';
import { useReferenceStore } from '@/stores/referenceStore';

// ── Typewriter Cycle ────────────────────────────────────────────────────

const PHRASES = [
  'Hi, Vonish',
  'Welcome back',
  "Let's get to work.",
  'What should we build today?',
];

const TYPE_SPEED = 80;   // ms per char
const PAUSE = 3500;       // ms pause after full phrase
const DELETE_SPEED = 40;  // ms per char delete

function useTypewriterCycle(phrases: string[]) {
  const [text, setText] = useState(phrases[0] ?? PHRASES[1]);
  const [cursor, setCursor] = useState(true);
  const phraseIdx = useRef(0);
  const charIdx = useRef((phrases[0] ?? PHRASES[1]).length);
  const deleting = useRef(false);
  const paused = useRef(true);

  useEffect(() => {
    const initial = phrases[0] ?? PHRASES[1];
    phraseIdx.current = 0;
    charIdx.current = initial.length;
    deleting.current = false;
    paused.current = true;
    setText(initial);
  }, [phrases]);

  // Blinking cursor
  useEffect(() => {
    const t = setInterval(() => setCursor((v) => !v), 530);
    return () => clearInterval(t);
  }, []);

  // Typewriter cycle
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;

    const tick = () => {
      const phrase = phrases[phraseIdx.current % phrases.length] ?? '';

      if (paused.current) {
        paused.current = false;
        deleting.current = true;
        timer = setTimeout(tick, PAUSE);
        return;
      }

      if (deleting.current) {
        charIdx.current--;
        setText(phrase.slice(0, Math.max(0, charIdx.current)));
        if (charIdx.current <= 0) {
          deleting.current = false;
          phraseIdx.current++;
          charIdx.current = 0;
          // resume typing immediately – don't enter paused/delete loop
          timer = setTimeout(tick, TYPE_SPEED * 3);
          return;
        }
        timer = setTimeout(tick, DELETE_SPEED);
        return;
      }

      // Typing
      charIdx.current++;
      setText(phrase.slice(0, charIdx.current));
      if (charIdx.current >= phrase.length) {
        paused.current = true;
        timer = setTimeout(tick, TYPE_SPEED * 2);
        return;
      }
      timer = setTimeout(tick, TYPE_SPEED);
    };

    timer = setTimeout(tick, 300);
    return () => clearTimeout(timer);
  }, [phrases]);

  return { text, cursor };
}

// ── Task Prompts ─────────────────────────────────────────────────────────

const MODE_CONTENT = {
  chat: {
    eyebrow: 'CHAT · Evidence Desk',
    phrases: ['What shall we think through?', 'Bring the evidence together.', 'Ask, compare, decide.'],
    note: '以对话为中心，适合问答、研究、总结、方案推演。工具、Workspace、上下文和模型配置都会走真实后端。',
    tryLabel: 'Start with',
    tasks: [
      {
        icon: PenLine,
        chip: 'Write',
        title: 'Write',
        desc: '写作、整理、润色',
        prompt: 'Help me write and polish this into a clear, useful response.',
      },
      {
        icon: GraduationCap,
        chip: 'Learn',
        title: 'Learn',
        desc: '解释概念、梳理知识',
        prompt: 'Teach me this topic clearly with examples and key distinctions.',
      },
      {
        icon: Code2,
        chip: 'Code',
        title: 'Code',
        desc: '代码问答与实现建议',
        prompt: 'Help me reason through a coding task and propose a practical implementation.',
      },
      {
        icon: Search,
        chip: 'Research',
        title: 'Research & summarize',
        desc: '多源搜索、爬取、证据整理',
        prompt: 'Research this topic with web search and evidence, then summarize the key findings with citations.',
      },
      {
        icon: ClipboardList,
        chip: "Agent's choice",
        title: 'Plan a task',
        desc: '拆解目标、列风险、给执行顺序',
        prompt: 'Help me plan this task. Break it down into steps, risks, and a practical execution order.',
      },
      {
        icon: FileText,
        title: 'Explain a document',
        desc: '读取 workspace 文件并提炼重点',
        prompt: 'Read the relevant files in the current workspace and explain the important points clearly.',
      },
    ],
  },
  work: {
    eyebrow: 'WORK · Local Office',
    phrases: ["What's on your desk today?", 'Turn files into decisions.', 'Draft, organize, deliver.'],
    note: '以日常办公为中心，适合资料整理、文档/PPT/表格处理、报告产出和文件交付。',
    tryLabel: 'Pick a task',
    tasks: [
      {
        icon: Presentation,
        chip: 'Deck',
        title: 'Make a presentation',
        desc: '从资料生成 PPT 或演示结构',
        prompt: 'Create a presentation plan from the workspace materials, then generate a polished slide deck outline.',
      },
      {
        icon: FileText,
        chip: 'Report',
        title: 'Draft a report',
        desc: '提纲、正文、证据、交付物',
        prompt: 'Draft a structured report from the current workspace materials. Include assumptions, evidence, and next steps.',
      },
      {
        icon: FolderTree,
        chip: 'Organize',
        title: 'Organize files',
        desc: '检查 workspace，整理目录和文件说明',
        prompt: 'Inspect the current workspace files, summarize what is inside, and propose a clean organization plan.',
      },
    ],
  },
  code: {
    eyebrow: 'CODE · Local Runtime',
    phrases: ["What's up next, Vonish?", 'Inspect, patch, verify.', 'Ship the local fix.'],
    note: '以开发编程为中心，适合代码理解、修复、重构、测试、Git 检查和本地工具调用。',
    tryLabel: 'Open a session',
    tasks: [
      {
        icon: Terminal,
        chip: 'Inspect',
        title: 'Analyze a codebase',
        desc: '搜索结构、识别模式和风险',
        prompt: 'Analyze the current workspace codebase. Map the architecture, identify key patterns, potential issues, and suggest improvements.',
      },
      {
        icon: Bug,
        chip: 'Debug',
        title: 'Debug & fix errors',
        desc: '追踪日志、修复、验证',
        prompt: 'Search through build logs and error traces. Identify root causes of failures, apply fixes, and verify the solution works.',
      },
      {
        icon: GitBranch,
        chip: 'Review',
        title: 'Review Git changes',
        desc: '查看 diff、风险和测试缺口',
        prompt: 'Review the current Git changes. Focus on bugs, regressions, risky diffs, and missing tests.',
      },
      {
        icon: Code2,
        chip: 'Build',
        title: 'Implement a feature',
        desc: '按现有代码风格完成落地',
        prompt: 'Implement the requested feature in the current codebase, following existing patterns and verifying the result.',
      },
    ],
  },
};

const ACCEPTED_FILES = '.txt,.md,.markdown,.pdf,.doc,.docx,.ppt,.pptx,.jpg,.jpeg,.png,.webp,.gif';

// ── Component ────────────────────────────────────────────────────────────

export function WelcomeScreen() {
  const {
    sendMessage,
    stopGeneration,
    isStreaming,
    inputText,
    setInputText,
    selectedModelId,
    models,
    attachments,
    addAttachment,
    removeAttachment,
  } = useChatStore();
  const referenceCount = useReferenceStore((state) => state.references.length);
  const activeMode = useUIStore((state) => state.activeMode);
  const content = MODE_CONTENT[activeMode];
  const { text, cursor } = useTypewriterCycle(content.phrases);
  const [visible, setVisible] = useState(false);
  const [draft, setDraft] = useState(inputText);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selectedModel = models.find((model) => model.id === selectedModelId);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 100);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (inputText !== draft) setDraft(inputText);
  }, [draft, inputText]);

  const sendDraft = useCallback(() => {
    const trimmed = draft.trim();
    if ((!trimmed && attachments.length === 0 && referenceCount === 0) || isStreaming) return;
    void sendMessage(trimmed);
    setDraft('');
    setInputText('');
  }, [attachments.length, draft, isStreaming, referenceCount, sendMessage, setInputText]);

  const handleFilesSelected = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      Array.from(event.target.files ?? []).forEach((file) => addAttachment(file));
      event.target.value = '';
    },
    [addAttachment],
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key !== 'Enter') return;
      if (event.shiftKey || event.ctrlKey || event.metaKey) return;
      event.preventDefault();
      sendDraft();
    },
    [sendDraft],
  );

  const placeholder =
    activeMode === 'work'
      ? 'How can I help with your files today?'
      : activeMode === 'code'
        ? 'Describe a task or ask a question'
        : 'Type / for skills';

  return (
    <div className="flex-1 overflow-y-auto px-4 py-10">
      <div
        className={cn(
          'mx-auto flex min-h-full w-full max-w-[860px] flex-col items-center justify-center transition-opacity duration-700',
          visible ? 'opacity-100' : 'opacity-0',
        )}
      >
        <div className="mb-9 text-center">
          <div className="mb-3 font-mono-code text-[11px] uppercase tracking-[0.18em] text-foreground-subtle">{content.eyebrow}</div>
          <h1 className="font-evidence-title min-h-[58px] text-[42px] font-semibold leading-tight text-foreground md:text-[48px]">
            <Sparkles className="mr-4 inline h-8 w-8 -translate-y-1 text-[#c9784b]" />
            {text}
            <span
              className={cn(
                'ml-1 text-primary transition-opacity',
                cursor ? 'opacity-100' : 'opacity-0'
              )}
            >
              |
            </span>
          </h1>
          <p className="mx-auto mt-2 max-w-xl text-[13px] leading-6 text-foreground-muted">
            {content.note}
          </p>
        </div>

        <div
          className={cn(
            'w-full transition-all delay-300 duration-500',
            visible ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0',
          )}
        >
          {(attachments.length > 0 || referenceCount > 0) && (
            <ComposerContextBar
              attachments={attachments.map((attachment) => ({
                id: attachment.id,
                name: attachment.file.name,
                type: attachment.file.type || 'application/octet-stream',
                size: attachment.file.size,
                uploading: attachment.uploading,
              }))}
              onRemoveAttachment={removeAttachment}
              className="rounded-t-[18px] border border-b-0 border-white/10 bg-[#2c2c2b]"
            />
          )}
          <div
            className={cn(
              'border border-white/10 bg-[#2c2c2b] p-4 shadow-[0_18px_44px_rgba(0,0,0,0.28)]',
              attachments.length > 0 || referenceCount > 0 ? 'rounded-b-[20px] rounded-t-none' : 'rounded-[20px]',
            )}
          >
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(event) => {
                setDraft(event.target.value);
                setInputText(event.target.value);
              }}
              onKeyDown={handleKeyDown}
              disabled={isStreaming}
              rows={3}
              placeholder={isStreaming ? 'Generating...' : placeholder}
              className="min-h-[72px] w-full resize-none bg-transparent text-[18px] leading-7 text-[#d6d2ca] outline-none placeholder:text-[#918d86] disabled:opacity-55"
            />
            <div className="mt-2 flex items-center justify-between gap-3">
              <div className="flex items-center gap-1">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ACCEPTED_FILES}
                  multiple
                  className="hidden"
                  onChange={handleFilesSelected}
                />
                <button
                  type="button"
                  className="grid h-8 w-8 place-items-center rounded-md text-[#d8d4cf] transition-colors hover:bg-white/10"
                  aria-label="Add file"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isStreaming}
                >
                  <Plus className="h-5 w-5" />
                </button>
              </div>
              <div className="flex min-w-0 items-center gap-2">
                <ConfigPanel />
                <span className="hidden max-w-[180px] truncate text-[13px] font-medium text-[#c9c4ba] sm:block">
                  {selectedModel?.name ?? selectedModelId}
                </span>
                <button
                  type="button"
                  className="grid h-8 w-8 place-items-center rounded-md text-[#d8d4cf] transition-colors hover:bg-white/10"
                  aria-label="Voice"
                >
                  <Mic className="h-4 w-4" />
                </button>
                {isStreaming ? (
                  <button
                    type="button"
                    onClick={stopGeneration}
                    className="grid h-8 w-8 place-items-center rounded-md bg-error text-white transition-colors hover:bg-error/80"
                    aria-label="Stop"
                  >
                    <Square className="h-3.5 w-3.5" fill="currentColor" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={sendDraft}
                    disabled={!draft.trim() && attachments.length === 0 && referenceCount === 0}
                    className={cn(
                      'grid h-8 w-8 place-items-center rounded-md transition-colors',
                      draft.trim() || attachments.length > 0 || referenceCount > 0
                        ? 'bg-[#d8d4cf] text-[#1f1f1d] hover:bg-white'
                        : 'cursor-not-allowed bg-white/10 text-[#918d86]',
                    )}
                    aria-label="Send"
                  >
                    <Send className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {content.tasks.slice(0, 5).map((task) => (
              <button
                key={task.title}
                onClick={() => sendMessage(task.prompt)}
                className="group inline-flex h-9 items-center gap-2 rounded-lg bg-[#333331] px-3 text-[13px] font-semibold text-[#d6d2ca] transition-colors hover:bg-[#42423f] hover:text-white"
              >
                <task.icon className="h-4 w-4 text-[#a7a39c] transition-colors group-hover:text-[#d8d4cf]" />
                {task.chip ?? task.title}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
