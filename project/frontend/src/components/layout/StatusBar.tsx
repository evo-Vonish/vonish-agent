import { useState, useRef, useEffect } from 'react';
import { Globe, User, Settings, ChevronUp, LogOut } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { Tooltip } from '@/components/ui/Tooltip';

interface StatusBarProps {
  className?: string;
}

/** Small popover menu — Claude Code style */
function PopoverMenu({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    if (open) document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div
      ref={ref}
      className="absolute bottom-full left-0 mb-2 w-56 bg-surface-elevated border border-border rounded-xl shadow-2xl py-1 z-50 animate-in fade-in slide-in-from-bottom-2 duration-150"
    >
      {children}
    </div>
  );
}

export function StatusBar({ className }: StatusBarProps) {
  const { isMobile, toggleRightPanel } = useUIStore();
  const [acctOpen, setAcctOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);

  const languages = [
    { label: 'English', code: 'en' },
    { label: '中文 (简体)', code: 'zh' },
    { label: '日本語', code: 'ja' },
    { label: '한국어', code: 'ko' },
    { label: 'Français', code: 'fr' },
    { label: 'Deutsch', code: 'de' },
  ];
  const [lang, setLang] = useState('zh');

  if (isMobile) {
    return (
      <footer
        className={cn(
          'h-9 flex items-center justify-between px-3 border-t border-border bg-background flex-shrink-0',
          className
        )}
      >
        <button
          onClick={toggleRightPanel}
          className="flex items-center gap-1 px-2 py-1 rounded-full bg-surface border border-border text-[10px] text-foreground-muted hover:text-foreground transition-colors"
        >
          <Settings className="w-3 h-3" />
          设置
        </button>
      </footer>
    );
  }

  return (
    <footer
      className={cn(
        'h-8 flex items-center justify-between px-3 border-t border-border bg-background flex-shrink-0 z-20',
        className
      )}
    >
      {/* Left: Claude Code style buttons — Account / Settings / Language */}
      <div className="flex items-center gap-1">
        {/* Account */}
        <div className="relative">
          <Tooltip content="Account">
            <button
              onClick={() => { setAcctOpen(!acctOpen); setLangOpen(false); }}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] transition-colors',
                acctOpen
                  ? 'text-foreground bg-surface-hover'
                  : 'text-foreground-muted hover:text-foreground hover:bg-surface-hover'
              )}
            >
              <User className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Account</span>
            </button>
          </Tooltip>
          <PopoverMenu open={acctOpen} onClose={() => setAcctOpen(false)}>
            <div className="px-3 py-2 border-b border-border">
              <p className="text-xs font-semibold text-foreground">Developer</p>
              <p className="text-[10px] text-foreground-subtle">dev@example.com</p>
            </div>
            <button className="w-full flex items-center gap-2 px-3 py-2 text-xs text-foreground-muted hover:text-foreground hover:bg-surface-hover transition-colors">
              <LogOut className="w-3.5 h-3.5" />
              Sign out
            </button>
          </PopoverMenu>
        </div>

        {/* Settings */}
        <Tooltip content="Settings">
          <button
            onClick={toggleRightPanel}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] text-foreground-muted hover:text-foreground hover:bg-surface-hover transition-colors"
          >
            <Settings className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Settings</span>
          </button>
        </Tooltip>

        {/* Language */}
        <div className="relative">
          <Tooltip content="Language">
            <button
              onClick={() => { setLangOpen(!langOpen); setAcctOpen(false); }}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] transition-colors',
                langOpen
                  ? 'text-foreground bg-surface-hover'
                  : 'text-foreground-muted hover:text-foreground hover:bg-surface-hover'
              )}
            >
              <Globe className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Language</span>
            </button>
          </Tooltip>
          <PopoverMenu open={langOpen} onClose={() => setLangOpen(false)}>
            {languages.map((l) => (
              <button
                key={l.code}
                onClick={() => { setLang(l.code); setLangOpen(false); }}
                className={cn(
                  'w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-surface-hover transition-colors',
                  lang === l.code ? 'text-foreground' : 'text-foreground-muted'
                )}
              >
                {l.label}
                {lang === l.code && <span className="w-1.5 h-1.5 rounded-full bg-primary" />}
              </button>
            ))}
          </PopoverMenu>
        </div>
      </div>

      {/* Right: simple collapse chevron for mobile-like expand (desktop only indicator) */}
      <div className="flex items-center">
        <Tooltip content="Collapse sidebar">
          <button className="p-1.5 rounded-md text-foreground-subtle hover:text-foreground hover:bg-surface-hover transition-colors">
            <ChevronUp className="w-3.5 h-3.5" />
          </button>
        </Tooltip>
      </div>
    </footer>
  );
}
