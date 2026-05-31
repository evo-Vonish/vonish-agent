import { useState, useEffect, useRef, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chatStore';
import { useI18n } from '@/i18n';
import { Zap, FolderTree, Terminal, Search, GitBranch, Bug } from 'lucide-react';

// ── Typewriter Cycle ────────────────────────────────────────────────────

const PHRASES = [
  'Hi, Vonish',
  'Welcome back',
  "Let's get to work.",
  'What should we build today?',
];

const TYPE_SPEED = 80;   // ms per char
const PAUSE = 1800;       // ms pause after full phrase
const DELETE_SPEED = 40;  // ms per char delete

function useTypewriterCycle() {
  const [text, setText] = useState('');
  const [cursor, setCursor] = useState(true);
  const phraseIdx = useRef(0);
  const charIdx = useRef(0);
  const deleting = useRef(false);
  const paused = useRef(false);

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
          paused.current = true;
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
    <div className="flex-1 flex flex-col items-center justify-center overflow-y-auto px-4">
      <div className={cn(
        'text-center space-y-8 max-w-2xl w-full transition-opacity duration-700',
        visible ? 'opacity-100' : 'opacity-0'
      )}>
        {/* Logo */}
        <div className="w-12 h-12 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center mx-auto">
          <Zap className="w-6 h-6 text-primary" />
        </div>

        {/* Typewriter title */}
        <div className="h-20 flex items-center justify-center">
          <h1 className="text-[56px] font-bold text-foreground leading-none tracking-tight">
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
        </div>

        {/* Task prompts */}
        <div className={cn(
          'grid gap-2 w-full transition-all duration-500 delay-300',
          visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
        )}>
          <p className="text-[11px] text-foreground-subtle uppercase tracking-wider text-center mb-1">
            {t('chat.try')}
          </p>
          {TASKS.map((task) => (
            <button
              key={task.title}
              onClick={() => sendMessage(task.prompt)}
              className="w-full flex items-start gap-3 px-4 py-3 rounded-xl bg-surface border border-border hover:border-primary/30 hover:bg-surface-hover transition-all group text-left"
            >
              <div className="w-8 h-8 rounded-lg bg-background border border-border flex items-center justify-center flex-shrink-0 mt-0.5 group-hover:border-primary/20 transition-colors">
                <task.icon className="w-4 h-4 text-foreground-muted group-hover:text-primary transition-colors" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium text-foreground group-hover:text-foreground transition-colors">
                  {task.title}
                </div>
                <div className="text-xs text-foreground-subtle mt-0.5 line-clamp-1">
                  {task.desc}
                </div>
              </div>
            </button>
          ))}
        </div>

        {/* Footer hint */}
        <p className="text-[10px] text-foreground-subtle">
          Type a message or pick a task above
        </p>
      </div>
    </div>
  );
}
