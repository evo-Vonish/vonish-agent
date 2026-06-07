import { useEffect, useRef, useState, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { TopBar } from './TopBar';
import { Sidebar } from './Sidebar';
import { DissonanceField } from './DissonanceField';
import { WorkbenchRightPanel } from './WorkbenchRightPanel';

const MIN_PANEL_WIDTH = 240;
const MAX_PANEL_WIDTH = 560;
const DEFAULT_PANEL_WIDTH = 288; // w-72

interface MainLayoutProps {
  children: React.ReactNode;
  className?: string;
}

export function MainLayout({ children, className }: MainLayoutProps) {
  const { rightPanelOpen, setIsMobile } = useUIStore();
  const [panelWidth, setPanelWidth] = useState(DEFAULT_PANEL_WIDTH);
  const dragging = useRef(false);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, [setIsMobile]);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragging.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const newWidth = window.innerWidth - e.clientX;
      setPanelWidth(Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, newWidth)));
    };
    const onMouseUp = () => {
      if (!dragging.current) return;
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
  }, []);

  return (
    <div
      className={cn(
        'relative h-screen w-screen overflow-hidden bg-[#0a0a0b] text-[#e8e6e3]',
        className
      )}
    >
      <DissonanceField />
      <div className="relative z-10 flex h-full overflow-hidden">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col border-l border-white/[0.055] bg-[#0e0e0f]/70 backdrop-blur-xl">
          <TopBar />
          <main className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
            {children}
          </main>
        </div>
        {rightPanelOpen && (
          <>
            <div
              onMouseDown={onMouseDown}
              className="group relative hidden w-1.5 flex-shrink-0 cursor-col-resize bg-transparent transition-colors hover:bg-primary/25 active:bg-primary/40 md:block"
            >
              <div className="absolute inset-y-0 left-1/2 w-px -translate-x-px bg-white/[0.06] group-hover:bg-primary/25" />
            </div>
            <div
              ref={panelRef}
              className="hidden flex-shrink-0 overflow-y-auto border-l border-white/[0.06] bg-[#0e0e0f]/75 backdrop-blur-xl md:block"
              style={{ width: panelWidth }}
            >
              <WorkbenchRightPanel />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
