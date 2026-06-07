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
        'z-30 flex h-10 flex-shrink-0 select-none items-center justify-between border-b border-white/[0.06] bg-[#0e0e0f]/60 px-3 backdrop-blur-xl',
        className
      )}
    >
      <div className="flex items-center gap-1.5">
        {!isMobile && (
          <Tooltip content={sidebarOpen ? t('nav.sidebar.collapse') : t('nav.sidebar.expand')}>
            <button
              onClick={toggleSidebar}
              className="rounded-md p-1.5 text-[#9a9590] transition-colors hover:bg-white/[0.06] hover:text-[#e8e6e3]"
            >
              <PanelLeft className="w-4 h-4" />
            </button>
          </Tooltip>
        )}
        {isMobile && (
          <Tooltip content={t('statusbar.more')}>
            <button
              onClick={() => setMobileSidebarOpen(true)}
              className="rounded-md p-1.5 text-[#9a9590] transition-colors hover:bg-white/[0.06] hover:text-[#e8e6e3]"
            >
              <MessageSquare className="w-4 h-4" />
            </button>
          </Tooltip>
        )}
        <Tooltip content={t('chat.new')}>
          <button
            onClick={handleNewChat}
            className="rounded-md p-1.5 text-[#9a9590] transition-colors hover:bg-white/[0.06] hover:text-[#e8e6e3]"
          >
            <Plus className="w-4 h-4" />
          </button>
        </Tooltip>
        <div className="mx-1 h-4 w-px bg-white/[0.08]" />
        <span className="max-w-[200px] truncate font-mono-code text-[12px] font-medium tracking-[0.02em] text-[#9a9590] sm:max-w-[360px]">
          {currentConv?.title ?? t('chat.title')}
        </span>
      </div>

      <div className="flex min-w-0 items-center gap-2">
        <span className="hidden max-w-[220px] truncate font-mono-code text-[11px] tracking-[0.02em] text-[#5c5855] sm:block">
          {model?.name ?? selectedModelId}
        </span>
        <Tooltip content="Settings">
          <button
            type="button"
            onClick={() => useWorkbenchStore.getState().openSpecialTab('settings')}
            className="rounded-md p-1.5 text-[#9a9590] transition-colors hover:bg-white/[0.06] hover:text-[#e8e6e3]"
          >
            <Settings className="h-4 w-4" />
          </button>
        </Tooltip>
        <Tooltip content="API / Tools">
          <button
            type="button"
            onClick={toggleRightPanel}
            className="rounded-md p-1.5 text-[#9a9590] transition-colors hover:bg-white/[0.06] hover:text-[#e8e6e3]"
          >
            <SlidersHorizontal className="h-4 w-4" />
          </button>
        </Tooltip>
      </div>
    </header>
  );
}
