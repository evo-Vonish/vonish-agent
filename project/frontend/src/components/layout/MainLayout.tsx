import { useEffect } from 'react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { TopBar } from './TopBar';
import { Sidebar } from './Sidebar';
import { StatusBar } from './StatusBar';
import { ContextManagerPanel } from '@/components/composer/ContextManagerPanel';

interface MainLayoutProps {
  children: React.ReactNode;
  className?: string;
}

export function MainLayout({ children, className }: MainLayoutProps) {
  const { rightPanelOpen, setIsMobile } = useUIStore();

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, [setIsMobile]);

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
          <div className="w-72 border-l border-border bg-surface flex-shrink-0 overflow-y-auto hidden md:block">
            <ContextManagerPanel />
          </div>
        )}
      </div>
      <StatusBar />
    </div>
  );
}
