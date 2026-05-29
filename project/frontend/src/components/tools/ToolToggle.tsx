import { cn } from '@/lib/utils';

interface ToolToggleProps {
  enabled: boolean;
  onToggle: () => void;
  disabled?: boolean;
}

export function ToolToggle({ enabled, onToggle, disabled = false }: ToolToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      disabled={disabled}
      onClick={onToggle}
      className={cn(
        'relative inline-flex h-5 w-9 items-center rounded-full transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        enabled ? 'bg-primary' : 'bg-foreground-subtle/30',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      <span
        className={cn(
          'inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform duration-200 ease-in-out',
          enabled ? 'translate-x-[18px]' : 'translate-x-[2px]'
        )}
      />
    </button>
  );
}
