import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

interface SmoothStreamingTextProps {
  text: string;
  active?: boolean;
  className?: string;
  chunkSize?: number;
}

export function SmoothStreamingText({
  text,
  active = false,
  className,
  chunkSize = 3,
}: SmoothStreamingTextProps) {
  const [visible, setVisible] = useState(active ? '' : text);
  const indexRef = useRef(active ? 0 : text.length);

  useEffect(() => {
    if (!active) {
      setVisible(text);
      indexRef.current = text.length;
      return;
    }

    let frame = 0;
    const tick = () => {
      const current = indexRef.current;
      if (current >= text.length) {
        frame = window.setTimeout(tick, 40);
        return;
      }
      const next = Math.min(text.length, current + chunkSize);
      indexRef.current = next;
      setVisible(text.slice(0, next));
      frame = window.setTimeout(tick, 18);
    };

    frame = window.setTimeout(tick, 18);
    return () => window.clearTimeout(frame);
  }, [active, chunkSize, text]);

  return (
    <span className={cn(active && 'smooth-streaming-text', className)}>
      {visible}
    </span>
  );
}
