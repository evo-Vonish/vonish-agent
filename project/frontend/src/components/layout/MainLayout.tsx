import { useEffect, useRef, useState, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { TopBar } from './TopBar';
import { Sidebar } from './Sidebar';
import { StatusBar } from './StatusBar';
import { ContextManagerPanel } from '@/components/composer/ContextManagerPanel';

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
        'h-screen w-screen flex flex-col bg-background text-foreground overflow-hidden',
        className
      )}
    >
      <TopBar />
      <div className="flex-1 flex overflow-hidden">
        <Sidebar />
        <main className="flex-1 flex flex-col overflow-hidden relative min-w-0">
          {children}
        </main>
        {rightPanelOpen && (
          <>
            {/* Drag handle */}
            <div
              onMouseDown={onMouseDown}
              className="hidden md:block w-1.5 cursor-col-resize hover:bg-primary/30 active:bg-primary/50 bg-transparent transition-colors flex-shrink-0 relative group"
            >
              <div className="absolute inset-y-0 left-1/2 -translate-x-px w-px bg-border group-hover:bg-primary/20" />
            </div>
            {/* Panel */}
            <div
              ref={panelRef}
              className="border-l border-border bg-surface flex-shrink-0 overflow-y-auto hidden md:block"
              style={{ width: panelWidth }}
            >
              <ContextManagerPanel />
            </div>
          </>
        )}
      </div>
      <StatusBar />
    </div>
  );
}
