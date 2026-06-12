import { useCallback, useEffect, useRef } from 'react';
import { useUIStore } from '@/stores/uiStore';
import { useWorkbenchStore } from '@/stores/workbenchStore';
import { MessageStream } from '@/components/chat';
import { Composer } from '@/components/composer';
import { WorkbenchPanel, SelectionToolbar, InlineAIPrompt } from '@/components/workbench';
import { DissonanceField } from './DissonanceField';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { ContextToastHost } from './ContextToastHost';
import { useChatStore } from '@/stores/chatStore';

export function AgentIDEShell() {
  const { rightPanelOpen, setIsMobile } = useUIStore();
  const hasMessages = useChatStore((state) => state.messages.length > 0);
  const panelWidth = useWorkbenchStore((state) => state.panelWidth);
  const setPanelWidth = useWorkbenchStore((state) => state.setPanelWidth);
  const dragging = useRef(false);

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, [setIsMobile]);

  const onMouseDown = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    dragging.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    const onMouseMove = (event: MouseEvent) => {
      if (!dragging.current) return;
      setPanelWidth(window.innerWidth - event.clientX);
    };
    const onMouseUp = () => {
      dragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [setPanelWidth]);

  return (
    <div className="h-screen w-screen overflow-hidden bg-background text-foreground">
      <DissonanceField />
      <SelectionToolbar />
      <InlineAIPrompt />
      <ContextToastHost />
      <div className="relative z-10 flex h-full">
        <Sidebar />
        <main className="flex min-w-0 flex-1 flex-col border-l border-border/70 bg-background/72 backdrop-blur-[10px]">
          <TopBar />
          <div className="relative flex min-h-0 flex-1 flex-col">
            <MessageStream />
            {hasMessages && <Composer />}
          </div>
        </main>

        {rightPanelOpen && (
          <>
            <div onMouseDown={onMouseDown} className="group relative hidden w-1.5 shrink-0 cursor-col-resize bg-transparent md:block">
              <div className="absolute inset-y-0 left-1/2 w-px -translate-x-px bg-border transition-colors group-hover:bg-primary/35" />
            </div>
            <aside
              className="hidden h-full shrink-0 flex-col border-l border-border bg-background/78 shadow-[inset_1px_0_0_rgba(231,225,208,0.025)] backdrop-blur-xl md:flex"
              style={{ width: panelWidth }}
            >
              <WorkbenchPanel />
            </aside>
          </>
        )}
      </div>
    </div>
  );
}
