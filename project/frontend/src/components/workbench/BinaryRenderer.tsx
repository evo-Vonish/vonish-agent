import { File, FileText, FileType2 } from 'lucide-react';
import { formatBytes } from '@/lib/utils';
import type { WorkbenchTab } from '@/stores/workbenchStore';

export function BinaryRenderer({ tab }: { tab: WorkbenchTab }) {
  const label = tab.kind === 'pdf' ? 'PDF' : tab.kind === 'office' ? 'Office 文档' : '二进制文件';
  const Icon = tab.kind === 'pdf' ? FileType2 : tab.kind === 'office' ? FileText : File;

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
      <Icon className="h-12 w-12 text-[#5c5855]" />
      <div className="text-[14px] text-[#e8e6e3]">{tab.title}</div>
      <div className="font-mono-code text-[11px] text-[#5c5855]">
        {label}
        {tab.size !== undefined ? ` · ${formatBytes(tab.size)}` : ''}
        {tab.mimeType ? ` · ${tab.mimeType}` : ''}
      </div>
      <div className="mt-2 max-w-[320px] text-[12px] leading-5 text-[#9a9590]">
        此文件类型的工作台预览将在后续阶段提供。该文件仍可作为引用对象使用。
      </div>
    </div>
  );
}
