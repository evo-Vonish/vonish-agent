import { useState, useEffect, useRef, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chatStore';
import { useI18n } from '@/i18n';
import { FolderTree, Terminal, Search, GitBranch, Bug } from 'lucide-react';

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

function useTypewriterCycle() {
  const [text, setText] = useState(PHRASES[1]);
  const [cursor, setCursor] = useState(true);
  const phraseIdx = useRef(1);
  const charIdx = useRef(PHRASES[1].length);
  const deleting = useRef(false);
  const paused = useRef(true);

  // Blinking cursor
  useEffect(() => {
    const t = setInterval(() => setCursor((v) => !v), 530);
    return () => clearInterval(t);
  }, []);

  // Typewriter cycle
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;

    const tick = () => {
      const phrase = PHRASES[phraseIdx.current % PHRASES.length];

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
  }, []);

  return { text, cursor };
}

// ── Task Prompts ─────────────────────────────────────────────────────────

const TASKS = [
  {
    icon: FolderTree,
    title: 'Build a full-stack app',
    desc: 'Scaffold React + FastAPI, set up routing, auth, database',
    prompt: 'Create a full-stack web app with React frontend and FastAPI backend. Set up project structure, routing, authentication, and SQLite database.',
  },
  {
    icon: Terminal,
    title: 'Analyze a codebase',
    desc: 'Search, map structure, identify patterns and issues',
    prompt: 'Analyze the current workspace codebase. Map the architecture, identify key patterns, potential issues, and suggest improvements.',
  },
  {
    icon: Search,
    title: 'Research & summarize',
    desc: 'Web search multiple sources, compile findings',
    prompt: 'Research the latest best practices for building AI agent workbenches. Search multiple sources, compare approaches, and summarize findings.',
  },
  {
    icon: GitBranch,
    title: 'Refactor legacy code',
    desc: 'Identify dead code, modernize patterns, add types',
    prompt: 'Scan the workspace for legacy patterns. Identify dead code, suggest TypeScript type improvements, and refactor for modern best practices.',
  },
  {
    icon: Bug,
    title: 'Debug & fix errors',
    desc: 'Search logs, trace errors, apply fixes, verify',
    prompt: 'Search through build logs and error traces. Identify root causes of failures, apply fixes, and verify the solution works.',
  },
];

// ── Component ────────────────────────────────────────────────────────────

export function WelcomeScreen() {
  const { sendMessage } = useChatStore();
  const { t } = useI18n();
  const { text, cursor } = useTypewriterCycle();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 100);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-10">
      <div
        className={cn(
          'message-stream-shell mx-auto flex min-h-full w-full flex-col justify-center transition-opacity duration-700',
          visible ? 'opacity-100' : 'opacity-0',
        )}
      >
        <div className="mb-10">
          <div className="mb-3 font-mono-code text-[11px] uppercase tracking-[0.18em] text-[#5c5855]">VonishAgent</div>
          <h1 className="min-h-[48px] text-[38px] font-semibold leading-tight text-[#e8e6e3]">
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
          <p className="mt-2 max-w-xl text-[13px] leading-6 text-[#9a9590]">
            选择一个任务开始，或直接在下方输入。所有工具、Workspace、上下文和模型配置都会走真实后端。
          </p>
        </div>

        <div
          className={cn(
            'grid w-full gap-2 transition-all delay-300 duration-500',
            visible ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0',
          )}
        >
          <p className="mb-1 font-mono-code text-[11px] uppercase tracking-[0.12em] text-[#5c5855]">
            {t('chat.try')}
          </p>
          {TASKS.map((task) => (
            <button
              key={task.title}
              onClick={() => sendMessage(task.prompt)}
              className="group flex w-full items-start gap-3 rounded-md border border-white/[0.055] bg-white/[0.028] px-4 py-3 text-left transition-all hover:border-primary/30 hover:bg-white/[0.055]"
            >
              <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md border border-white/[0.06] bg-black/20 transition-colors group-hover:border-primary/25">
                <task.icon className="h-4 w-4 text-[#9a9590] transition-colors group-hover:text-primary" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium text-[#e8e6e3]">
                  {task.title}
                </div>
                <div className="mt-0.5 line-clamp-1 text-xs text-[#5c5855]">
                  {task.desc}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
