import { useCallback } from 'react';
import { PanelLeft, Plus, MessageSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';
import { useI18n } from '@/i18n';
import { Tooltip } from '@/components/ui/Tooltip';

interface TopBarProps {
  className?: string;
}

export function TopBar({ className }: TopBarProps) {
  const { toggleSidebar, sidebarOpen, isMobile, setMobileSidebarOpen } = useUIStore();
  const { createConversation, currentConversationId, conversations } = useChatStore();
  const { t } = useI18n();
  const currentConv = conversations.find((c) => c.id === currentConversationId);

  const handleNewChat = useCallback(() => {
    createConversation();
  }, [createConversation]);

  return (
    <header
      className={cn(
        'h-[42px] flex items-center justify-between px-3 border-b border-border bg-background/90 backdrop-blur-md z-30 flex-shrink-0 select-none',
        className
      )}
    >
      {/* Left section */}
      <div className="flex items-center gap-1.5">
        {!isMobile && (
          <Tooltip content={sidebarOpen ? t('nav.sidebar.collapse') : t('nav.sidebar.expand')}>
            <button
              onClick={toggleSidebar}
              className="p-1.5 rounded-md hover:bg-surface-hover text-foreground-muted hover:text-foreground transition-colors"
            >
              <PanelLeft className="w-4 h-4" />
            </button>
          </Tooltip>
        )}
        {isMobile && (
          <Tooltip content={t('statusbar.more')}>
            <button
              onClick={() => setMobileSidebarOpen(true)}
              className="p-1.5 rounded-md hover:bg-surface-hover text-foreground-muted hover:text-foreground transition-colors"
            >
              <MessageSquare className="w-4 h-4" />
            </button>
          </Tooltip>
        )}
        <Tooltip content={t('chat.new')}>
          <button
            onClick={handleNewChat}
            className="p-1.5 rounded-md hover:bg-surface-hover text-foreground-muted hover:text-foreground transition-colors"
          >
            <Plus className="w-4 h-4" />
          </button>
        </Tooltip>
        <div className="w-px h-4 bg-border mx-1" />
        <span className="text-xs text-foreground font-medium tracking-tight truncate max-w-[200px] sm:max-w-[300px]">
          {currentConv?.title ?? t('chat.title')}
        </span>
      </div>

    </header>
  );
}
