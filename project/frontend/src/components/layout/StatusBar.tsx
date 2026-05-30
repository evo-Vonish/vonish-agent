import { useState, useRef, useEffect } from 'react';
import { Globe, User, Settings, ChevronUp, LogOut } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { useLanguageStore } from '@/stores/languageStore';
import { useI18n } from '@/i18n';
import type { Locale } from '@/i18n';
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

const LANGUAGES: { labelKey: string; code: Locale }[] = [
  { labelKey: 'lang.en', code: 'en-US' },
  { labelKey: 'lang.zh', code: 'zh-CN' },
  { labelKey: 'lang.ja', code: 'ja-JP' },
  { labelKey: 'lang.ko', code: 'ko-KR' },
  { labelKey: 'lang.fr', code: 'fr-FR' },
  { labelKey: 'lang.de', code: 'de-DE' },
];

export function StatusBar({ className }: StatusBarProps) {
  const { isMobile, toggleRightPanel } = useUIStore();
  const { t } = useI18n();
  const locale = useLanguageStore((s) => s.locale);
  const setLocale = useLanguageStore((s) => s.setLocale);
  const [acctOpen, setAcctOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);

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
          {t('statusbar.settings')}
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
      <div className="flex items-center gap-1 i18n-fade">
        {/* Account */}
        <div className="relative">
          <Tooltip content={t('statusbar.account')}>
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
              <span className="hidden sm:inline">{t('statusbar.account')}</span>
            </button>
          </Tooltip>
          <PopoverMenu open={acctOpen} onClose={() => setAcctOpen(false)}>
            <div className="px-3 py-2 border-b border-border">
              <p className="text-xs font-semibold text-foreground">{t('statusbar.dev')}</p>
              <p className="text-[10px] text-foreground-subtle">{t('statusbar.email')}</p>
            </div>
            <button className="w-full flex items-center gap-2 px-3 py-2 text-xs text-foreground-muted hover:text-foreground hover:bg-surface-hover transition-colors">
              <LogOut className="w-3.5 h-3.5" />
              {t('statusbar.signout')}
            </button>
          </PopoverMenu>
        </div>

        {/* Settings */}
        <Tooltip content={t('statusbar.settings')}>
          <button
            onClick={toggleRightPanel}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] text-foreground-muted hover:text-foreground hover:bg-surface-hover transition-colors"
          >
            <Settings className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">{t('statusbar.settings')}</span>
          </button>
        </Tooltip>

        {/* Language */}
        <div className="relative">
          <Tooltip content={t('statusbar.language')}>
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
              <span className="hidden sm:inline">{t('statusbar.language')}</span>
            </button>
          </Tooltip>
          <PopoverMenu open={langOpen} onClose={() => setLangOpen(false)}>
            {LANGUAGES.map((l) => (
              <button
                key={l.code}
                onClick={() => { setLocale(l.code); setLangOpen(false); }}
                className={cn(
                  'w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-surface-hover transition-colors',
                  locale === l.code ? 'text-foreground' : 'text-foreground-muted'
                )}
              >
                {t(l.labelKey)}
                {locale === l.code && <span className="w-1.5 h-1.5 rounded-full bg-primary" />}
              </button>
            ))}
          </PopoverMenu>
        </div>
      </div>

      {/* Right: collapse hint */}
      <div className="flex items-center">
        <Tooltip content={t('statusbar.collapseHint')}>
          <button className="p-1.5 rounded-md text-foreground-subtle hover:text-foreground hover:bg-surface-hover transition-colors">
            <ChevronUp className="w-3.5 h-3.5" />
          </button>
        </Tooltip>
      </div>
    </footer>
  );
}
