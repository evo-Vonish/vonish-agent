import { cn } from '@/lib/utils';

interface ProgressProps {
  value: number;
  max?: number;
  className?: string;
  barClassName?: string;
  label?: string;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'default' | 'success' | 'warning' | 'error';
}

export function Progress({
  value,
  max = 100,
  className,
  barClassName,
  label,
  size = 'md',
  variant = 'default',
}: ProgressProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));

  const sizeClasses = {
    sm: 'h-1.5',
    md: 'h-2.5',
    lg: 'h-4',
  };

  const variantClasses = {
    default: 'bg-primary',
    success: 'bg-success',
    warning: 'bg-warning',
    error: 'bg-error',
  };

  return (
    <div className={cn('w-full', className)}>
      {label && (
        <div className="flex justify-between mb-1">
          <span className="text-xs text-foreground-muted">{label}</span>
          <span className="text-xs text-foreground-muted">{pct.toFixed(0)}%</span>
        </div>
      )}
      <div
        className={cn(
          'w-full rounded-full bg-surface-elevated overflow-hidden',
          sizeClasses[size]
        )}
      >
        <div
          className={cn(
            'rounded-full transition-all duration-500 ease-out',
            sizeClasses[size],
            variantClasses[variant],
            barClassName
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
