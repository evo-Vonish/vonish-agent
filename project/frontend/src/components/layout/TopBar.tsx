import { useCallback } from 'react';
import { PanelLeft, Plus, MessageSquare, Settings, SlidersHorizontal } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { useWorkbenchStore } from '@/stores/workbenchStore';
import { useChatStore } from '@/stores/chatStore';
import { useI18n } from '@/i18n';
import { Tooltip } from '@/components/ui/Tooltip';

interface TopBarProps {
  className?: string;
}

export function TopBar({ className }: TopBarProps) {
  const { toggleSidebar, sidebarOpen, isMobile, setMobileSidebarOpen, toggleRightPanel } = useUIStore();
  const { createConversation, currentConversationId, conversations, selectedModelId, models } = useChatStore();
  const { t } = useI18n();
  const currentConv = conversations.find((c) => c.id === currentConversationId);
  const model = models.find((item) => item.id === selectedModelId);

  const handleNewChat = useCallback(() => {
    createConversation();
  }, [createConversation]);

  return (
    <header
      className={cn(
        'z-30 flex h-12 flex-shrink-0 select-none items-center justify-between border-b border-border bg-background/70 px-3 backdrop-blur-xl',
        className
      )}
    >
      <div className="flex items-center gap-1.5">
        {!isMobile && (
          <Tooltip content={sidebarOpen ? t('nav.sidebar.collapse') : t('nav.sidebar.expand')}>
            <button
              onClick={toggleSidebar}
              className="rounded-md p-1.5 text-foreground-muted transition-colors hover:bg-primary/10 hover:text-primary"
            >
              <PanelLeft className="w-4 h-4" />
            </button>
          </Tooltip>
        )}
        {isMobile && (
          <Tooltip content={t('statusbar.more')}>
            <button
              onClick={() => setMobileSidebarOpen(true)}
              className="rounded-md p-1.5 text-foreground-muted transition-colors hover:bg-primary/10 hover:text-primary"
            >
              <MessageSquare className="w-4 h-4" />
            </button>
          </Tooltip>
        )}
        <Tooltip content={t('chat.new')}>
          <button
            onClick={handleNewChat}
            className="rounded-md p-1.5 text-foreground-muted transition-colors hover:bg-primary/10 hover:text-primary"
          >
            <Plus className="w-4 h-4" />
          </button>
        </Tooltip>
        <div className="mx-1 h-4 w-px bg-border" />
        <span className="max-w-[200px] truncate font-mono-code text-[12px] font-medium tracking-[0.02em] text-foreground-muted sm:max-w-[360px]">
          {currentConv?.title ?? t('chat.title')}
        </span>
      </div>

      <div className="flex min-w-0 items-center gap-2">
        <span className="hidden max-w-[220px] truncate font-mono-code text-[11px] tracking-[0.02em] text-foreground-subtle sm:block">
          {model?.name ?? selectedModelId}
        </span>
        <Tooltip content="Settings">
          <button
            type="button"
            onClick={() => useWorkbenchStore.getState().openSpecialTab('settings')}
            className="rounded-md p-1.5 text-foreground-muted transition-colors hover:bg-primary/10 hover:text-primary"
          >
            <Settings className="h-4 w-4" />
          </button>
        </Tooltip>
        <Tooltip content="API / Tools">
          <button
            type="button"
            onClick={toggleRightPanel}
            className="rounded-md p-1.5 text-foreground-muted transition-colors hover:bg-primary/10 hover:text-primary"
          >
            <SlidersHorizontal className="h-4 w-4" />
          </button>
        </Tooltip>
      </div>
    </header>
  );
}
