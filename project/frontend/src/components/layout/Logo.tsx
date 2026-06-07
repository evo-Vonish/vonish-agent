import type { CSSProperties } from 'react';

interface LogoProps {
  size?: number;
  variant?: 'cursor' | 'toolnode' | 'shieldorbit';
  className?: string;
  style?: CSSProperties;
}

const STROKE = '#c66a38';
const STROKE_SECONDARY = 'rgba(198, 106, 56, 0.45)';
const ACCENT_FILL = 'rgba(198, 106, 56, 0.12)';

export function Logo({ size = 20, variant = 'shieldorbit', className, style }: LogoProps) {
  const s = { width: size, height: size, ...style };
  if (variant === 'cursor') return <LogoCursor className={className} style={s} />;
  if (variant === 'toolnode') return <LogoToolNode className={className} style={s} />;
  return <LogoShieldOrbit className={className} style={s} />;
}

function LogoCursor({ style, className }: { style?: CSSProperties; className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" className={className} style={style}>
      <path d="M3 3L8.5 16L10 17" stroke={STROKE} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M17 3L11.5 16L10 17" stroke={STROKE} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M10 8L10.8 14.5L12.3 12.3L14.5 12.8L10 8Z" fill={ACCENT_FILL} stroke={STROKE} strokeWidth="1.2" strokeLinejoin="round" />
      <circle cx="14.8" cy="13.2" r="1" fill={STROKE} />
    </svg>
  );
}

function LogoToolNode({ style, className }: { style?: CSSProperties; className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" className={className} style={style}>
      <circle cx="10" cy="10" r="2.2" fill={ACCENT_FILL} stroke={STROKE} strokeWidth="1.3" />
      <line x1="10" y1="7.8" x2="10" y2="4" stroke={STROKE} strokeWidth="1.2" strokeLinecap="round" />
      <line x1="8.1" y1="11.2" x2="4.5" y2="14" stroke={STROKE} strokeWidth="1.2" strokeLinecap="round" />
      <line x1="11.9" y1="11.2" x2="15.5" y2="14" stroke={STROKE} strokeWidth="1.2" strokeLinecap="round" />
      <rect x="7.5" y="1.5" width="5" height="3" rx="0.8" fill={ACCENT_FILL} stroke={STROKE} strokeWidth="1.1" />
      <rect x="1.5" y="12.5" width="4" height="5" rx="0.8" fill={ACCENT_FILL} stroke={STROKE} strokeWidth="1.1" />
      <rect x="14.5" y="12.5" width="4" height="5" rx="0.8" fill={ACCENT_FILL} stroke={STROKE} strokeWidth="1.1" />
      <line x1="15.5" y1="14.5" x2="17.5" y2="14.5" stroke={STROKE_SECONDARY} strokeWidth="0.8" strokeLinecap="round" />
      <line x1="15.5" y1="15.8" x2="16.8" y2="15.8" stroke={STROKE_SECONDARY} strokeWidth="0.8" strokeLinecap="round" />
    </svg>
  );
}

function LogoShieldOrbit({ style, className }: { style?: CSSProperties; className?: string }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" className={className} style={style}>
      <path d="M10 2L3 4.5V9.8C3 14.2 6 17.5 10 18.5C14 17.5 17 14.2 17 9.8V4.5L10 2Z" fill="rgba(198, 106, 56, 0.06)" stroke={STROKE} strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M7 8L10 13L13 8" stroke={STROKE} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <ellipse cx="10" cy="10" rx="6" ry="3.5" stroke={STROKE_SECONDARY} strokeWidth="0.7" strokeDasharray="3 2" transform="rotate(-15 10 10)" />
      <circle cx="15" cy="7.5" r="0.9" fill={STROKE} />
    </svg>
  );
}
