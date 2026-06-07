import { useState } from 'react';
import { Code2, Eye } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer';
import { useWorkbenchStore, type WorkbenchTab } from '@/stores/workbenchStore';
import { CodeEditor } from './CodeEditor';
import { ProposedEditBar } from './ProposedEditBar';

export function MarkdownPreviewRenderer({ tab }: { tab: WorkbenchTab }) {
  const [mode, setMode] = useState<'preview' | 'source'>('preview');
  const updateContent = useWorkbenchStore((s) => s.updateContent);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ProposedEditBar tabId={tab.id} />
      <div className="flex shrink-0 items-center gap-1 border-b border-white/[0.06] px-3 py-1.5">
        {(['preview', 'source'] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={cn(
              'flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11.5px] transition-colors',
              mode === m ? 'bg-white/[0.07] text-[#e8e6e3]' : 'text-[#5c5855] hover:text-[#9a9590]',
            )}
          >
            {m === 'preview' ? <Eye className="h-3.5 w-3.5" /> : <Code2 className="h-3.5 w-3.5" />}
            {m === 'preview' ? 'Preview' : 'Source'}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {mode === 'preview' ? (
          <div
            className="px-5 py-4"
            data-quote-source="markdown-block"
            data-quote-file={tab.path}
            data-quote-ws={tab.workspaceId ?? ''}
          >
            <MarkdownRenderer content={tab.content ?? ''} />
          </div>
        ) : (
          <CodeEditor
            value={tab.content ?? ''}
            language="markdown"
            readOnly={tab.readonly}
            onChange={(value) => updateContent(tab.id, value)}
            quoteSource={tab.path ? { filePath: tab.path, title: tab.title, workspaceId: tab.workspaceId } : undefined}
          />
        )}
      </div>
    </div>
  );
}
