import { WorkbenchPanel } from '@/components/workbench';

/**
 * Legacy wrapper kept for backwards compatibility — `MainLayout` still imports
 * this name. The workbench implementation now lives in `components/workbench`.
 */
export function WorkbenchRightPanel() {
  return <WorkbenchPanel />;
}
