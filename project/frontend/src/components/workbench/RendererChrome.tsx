import type { ReactNode } from 'react';
import { AlertTriangle, Info, Loader2 } from 'lucide-react';

export function CenteredMessage({ children, spinning }: { children: ReactNode; spinning?: boolean }) {
  return (
    <div className="flex h-full items-center justify-center gap-2 p-6 text-center text-[12px] text-[#9a9590]">
      {spinning && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </div>
  );
}

export function ErrorView({ message }: { message: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-[12px] text-[#c97a76]">
      <AlertTriangle className="h-6 w-6" />
      {message}
    </div>
  );
}

export function LimitationBanner({ text }: { text: string }) {
  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-white/[0.06] bg-[#15130f] px-3 py-1.5 text-[11px] text-[#b8933e]">
      <Info className="h-3.5 w-3.5 shrink-0" />
      <span className="min-w-0 flex-1">{text}</span>
    </div>
  );
}
