import type { ReactNode } from 'react';

interface ExecutionCollapseProps {
  open: boolean;
  children: ReactNode;
}

export function ExecutionCollapse({ open, children }: ExecutionCollapseProps) {
  return (
    <div className="execution-collapse" data-open={open ? 'true' : 'false'}>
      <div className="execution-collapse-inner">{children}</div>
    </div>
  );
}
