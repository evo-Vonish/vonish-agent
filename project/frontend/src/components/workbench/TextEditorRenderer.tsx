import { useWorkbenchStore, type WorkbenchTab } from '@/stores/workbenchStore';
import { CodeEditor } from './CodeEditor';
import { ProposedEditBar } from './ProposedEditBar';

export function TextEditorRenderer({ tab }: { tab: WorkbenchTab }) {
  const updateContent = useWorkbenchStore((s) => s.updateContent);
  const reveal = useWorkbenchStore((s) => (s.reveal && s.reveal.tabId === tab.id ? s.reveal : null));

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ProposedEditBar tabId={tab.id} />
      <div className="min-h-0 flex-1">
        <CodeEditor
          value={tab.content ?? ''}
          language={tab.language}
          readOnly={tab.readonly}
          onChange={(value) => updateContent(tab.id, value)}
          reveal={reveal}
          quoteSource={tab.path ? { filePath: tab.path, title: tab.title, workspaceId: tab.workspaceId } : undefined}
        />
      </div>
    </div>
  );
}
