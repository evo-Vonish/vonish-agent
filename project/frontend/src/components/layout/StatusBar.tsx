import { useState, useRef, useEffect } from 'react';
import {
  Globe, User, Settings, ChevronUp, LogOut, ChevronRight,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { useLanguageStore } from '@/stores/languageStore';
import { useI18n } from '@/i18n';
import type { Locale } from '@/i18n';

interface StatusBarProps {
  className?: string;
}

const LANGUAGES: { labelKey: string; code: Locale }[] = [
  { labelKey: 'lang.en', code: 'en-US' },
  { labelKey: 'lang.zh', code: 'zh-CN' },
  { labelKey: 'lang.ja', code: 'ja-JP' },
  { labelKey: 'lang.ko', code: 'ko-KR' },
  { labelKey: 'lang.fr', code: 'fr-FR' },
  { labelKey: 'lang.de', code: 'de-DE' },
];

function langShortLabel(code: Locale): string {
  const map: Record<string, string> = {
    'en-US': 'English',
    'zh-CN': '中文',
    'ja-JP': '日本語',
    'ko-KR': '한국어',
    'fr-FR': 'Français',
    'de-DE': 'Deutsch',
  };
  return map[code] ?? code;
}

const PANEL_BG = '#252423';
const PANEL_BORDER = '1px solid rgba(255,255,255,0.07)';
const PANEL_SHADOW = '0 18px 48px rgba(0,0,0,0.50)';
const ITEM_HOVER_BG = 'rgba(255,255,255,0.05)';
const TEXT_PRIMARY = '#e2e0dd';
const TEXT_SECONDARY = '#a6a4a1';
const TEXT_MUTED = '#6f6d6b';
const ICON_COLOR = '#9d9b98';
const DIVIDER_COLOR = 'rgba(255,255,255,0.06)';
const DOT_COLOR = '#4795e6';

export function StatusBar({ className }: StatusBarProps) {
  const { isMobile, toggleRightPanel } = useUIStore();
  const { t } = useI18n();
  const locale = useLanguageStore((s) => s.locale);
  const setLocale = useLanguageStore((s) => s.setLocale);
  const [panelOpen, setPanelOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  // Click outside → close
  useEffect(() => {
    if (!panelOpen) return;
    const onMouse = (e: MouseEvent) => {
      if (
        panelRef.current && !panelRef.current.contains(e.target as Node) &&
        btnRef.current && !btnRef.current.contains(e.target as Node)
      ) {
        setPanelOpen(false);
        setLangOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setPanelOpen(false); setLangOpen(false); }
    };
    document.addEventListener('mousedown', onMouse);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onMouse);
      document.removeEventListener('keydown', onKey);
    };
  }, [panelOpen]);

  const closeAll = () => { setPanelOpen(false); setLangOpen(false); };

  // ── shared menu item styles ──
  const itemCls = cn(
    'w-full flex items-center gap-2.5 px-3 h-[38px] rounded-[9px] text-[13px] cursor-pointer transition-colors',
  );

  if (isMobile) {
    return (
      <footer className={cn('h-9 flex items-center justify-between px-3 border-t border-border bg-background flex-shrink-0', className)}>
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
    <footer className={cn('h-8 flex items-center justify-between px-2 border-t border-border bg-background flex-shrink-0 z-20', className)}>
      {/* ── Left: single Settings entry ── */}
      <div className="relative">
        <button
          ref={btnRef}
          onClick={() => setPanelOpen((v) => !v)}
          className={cn(
            'flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] transition-colors',
            panelOpen
              ? 'text-foreground bg-surface-hover'
              : 'text-foreground-muted hover:text-foreground hover:bg-surface-hover',
          )}
        >
          <Settings className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">{t('statusbar.settings')}</span>
        </button>

        {/* ── Codex-style settings popover ── */}
        {panelOpen && (
          <div
            ref={panelRef}
            className="absolute left-1 bottom-full mb-1.5 w-60 z-50"
            style={{
              background: PANEL_BG,
              border: PANEL_BORDER,
              borderRadius: 14,
              boxShadow: PANEL_SHADOW,
              padding: 8,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* User info */}
            <div className="px-3 pt-1 pb-2">
              <p className="text-[13px] font-medium leading-snug" style={{ color: TEXT_PRIMARY }}>
                {t('statusbar.dev')}
              </p>
              <p className="text-[11px] leading-snug" style={{ color: TEXT_SECONDARY }}>
                {t('statusbar.email')}
              </p>
            </div>

            {/* Account label */}
            <p
              className="px-3 pt-0.5 pb-1 text-[10px] font-semibold uppercase tracking-wide"
              style={{ color: TEXT_MUTED }}
            >
              {t('settings.panel.account')}
            </p>

            <div className="mx-3 my-0.5 border-t" style={{ borderColor: DIVIDER_COLOR }} />

            {/* Profile */}
            <button
              onClick={closeAll}
              className={itemCls}
              style={{ color: TEXT_SECONDARY, background: 'transparent' }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = ITEM_HOVER_BG;
                (e.currentTarget as HTMLButtonElement).style.color = TEXT_PRIMARY;
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                (e.currentTarget as HTMLButtonElement).style.color = TEXT_SECONDARY;
              }}
            >
              <User className="w-4 h-4 flex-shrink-0" style={{ color: ICON_COLOR }} />
              <span className="flex-1 text-left">{t('settings.panel.profile')}</span>
            </button>

            {/* Settings */}
            <button
              onClick={() => { toggleRightPanel(); closeAll(); }}
              className={itemCls}
              style={{ color: TEXT_SECONDARY, background: 'transparent' }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = ITEM_HOVER_BG;
                (e.currentTarget as HTMLButtonElement).style.color = TEXT_PRIMARY;
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                (e.currentTarget as HTMLButtonElement).style.color = TEXT_SECONDARY;
              }}
            >
              <Settings className="w-4 h-4 flex-shrink-0" style={{ color: ICON_COLOR }} />
              <span className="flex-1 text-left">{t('statusbar.settings')}</span>
              <span className="text-[11px]" style={{ color: TEXT_MUTED }}>Ctrl+,</span>
            </button>

            {/* Language */}
            <div className="relative">
              <button
                onClick={() => setLangOpen((v) => !v)}
                className={itemCls}
                style={{ color: TEXT_SECONDARY, background: 'transparent' }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = ITEM_HOVER_BG;
                  (e.currentTarget as HTMLButtonElement).style.color = TEXT_PRIMARY;
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                  (e.currentTarget as HTMLButtonElement).style.color = TEXT_SECONDARY;
                }}
              >
                <Globe className="w-4 h-4 flex-shrink-0" style={{ color: ICON_COLOR }} />
                <span className="flex-1 text-left">{t('statusbar.language')}</span>
                <span className="text-[11px] flex items-center gap-0.5" style={{ color: TEXT_MUTED }}>
                  {langShortLabel(locale)}
                  <ChevronRight className="w-3 h-3" />
                </span>
              </button>

              {langOpen && (
                <div
                  className="absolute left-full bottom-0 ml-1.5 w-40 animate-in fade-in slide-in-from-left-2 duration-150"
                  style={{
                    background: PANEL_BG,
                    border: PANEL_BORDER,
                    borderRadius: 14,
                    boxShadow: PANEL_SHADOW,
                    padding: 8,
                    zIndex: 51,
                  }}
                >
                  {LANGUAGES.map((l) => (
                    <button
                      key={l.code}
                      onClick={() => { setLocale(l.code); closeAll(); }}
                      className="w-full flex items-center justify-between px-3 h-[36px] rounded-[9px] text-[13px] transition-colors cursor-pointer"
                      style={{
                        color: locale === l.code ? TEXT_PRIMARY : TEXT_SECONDARY,
                        background: 'transparent',
                      }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLButtonElement).style.background = ITEM_HOVER_BG;
                        (e.currentTarget as HTMLButtonElement).style.color = TEXT_PRIMARY;
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                        (e.currentTarget as HTMLButtonElement).style.color = TEXT_SECONDARY;
                      }}
                    >
                      {t(l.labelKey)}
                      {locale === l.code && (
                        <span
                          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                          style={{ background: DOT_COLOR }}
                        />
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="mx-3 my-0.5 border-t" style={{ borderColor: DIVIDER_COLOR }} />

            {/* Sign out */}
            <button
              onClick={closeAll}
              className={itemCls}
              style={{ color: TEXT_SECONDARY, background: 'transparent' }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = ITEM_HOVER_BG;
                (e.currentTarget as HTMLButtonElement).style.color = TEXT_PRIMARY;
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                (e.currentTarget as HTMLButtonElement).style.color = TEXT_SECONDARY;
              }}
            >
              <LogOut className="w-4 h-4 flex-shrink-0" style={{ color: ICON_COLOR }} />
              <span className="flex-1 text-left">{t('statusbar.signout')}</span>
            </button>
          </div>
        )}
      </div>

      {/* ── Right: collapse hint ── */}
      <div className="flex items-center">
        <button className="p-1.5 rounded-md text-foreground-subtle hover:text-foreground hover:bg-surface-hover transition-colors">
          <ChevronUp className="w-3.5 h-3.5" />
        </button>
      </div>
    </footer>
  );
}
