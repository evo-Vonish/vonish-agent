import { useState, useRef } from 'react';
import {
  FileText,
  Globe,
  FolderOpen,
  Terminal,
  Code2,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ToolDefinition, ApprovalLevel } from '@/types/tools';
import { APPROVAL_LEVEL_COLORS, APPROVAL_LEVEL_LABELS } from '@/types/tools';
import { ToolToggle } from './ToolToggle';
import { useToolStore } from '@/stores/useToolStore';
import { useI18n } from '@/i18n';

const CATEGORY_ICON_MAP: Record<string, React.ComponentType<any>> = {
  file_ops: FolderOpen,
  workspace: LayoutIcon,
  python_ops: Code2,
  web_search: Globe,
  web_ops: Globe,
  shell_ops: Terminal,
  system: Terminal,
};

function LayoutIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
      <line x1="3" x2="21" y1="9" y2="9" />
      <line x1="9" x2="9" y1="21" y2="9" />
    </svg>
  );
}

interface ToolCardProps {
  tool: ToolDefinition;
}

export function ToolCard({ tool }: ToolCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const schemaRef = useRef<HTMLPreElement>(null);
  const toggleTool = useToolStore((s) => s.toggleTool);
  const { t } = useI18n();

  const IconComponent = CATEGORY_ICON_MAP[tool.category] || FileText;

  const handleCopySchema = async () => {
    const schemaText = JSON.stringify(tool.schema, null, 2);
    await navigator.clipboard.writeText(schemaText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const approvalColor = APPROVAL_LEVEL_COLORS[tool.approvalLevel as ApprovalLevel];
  const approvalLabel = APPROVAL_LEVEL_LABELS[tool.approvalLevel as ApprovalLevel];

  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-surface transition-all duration-200',
        'hover:border-border-hover hover:shadow-sm'
      )}
    >
      {/* Main row — use grid instead of flex to prevent squeeze-overlap */}
      <div
        className="grid items-center gap-2 px-3 py-2.5 cursor-pointer"
        style={{ gridTemplateColumns: '32px 1fr auto auto auto 20px' }}
        onClick={() => setExpanded(!expanded)}
      >
        {/* Icon */}
        <div className="w-8 h-8 rounded-md bg-primary/10 flex items-center justify-center">
          <IconComponent className="w-4 h-4 text-primary flex-shrink-0" />
        </div>

        {/* Name + Description — truncates to prevent overflow */}
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-semibold text-foreground truncate">{tool.name}</span>
            {tool.supportsParallel && (
              <Zap className="w-3 h-3 text-warning flex-shrink-0" />
            )}
          </div>
          <p className="text-xs text-foreground-muted truncate">{tool.description}</p>
        </div>

        {/* Approval Level Badge */}
        <span
          className={cn(
            'px-1.5 py-0.5 text-[10px] font-medium rounded-full border whitespace-nowrap',
            approvalColor
          )}
        >
          {approvalLabel}
        </span>

        {/* Toggle */}
        <div onClick={(e) => e.stopPropagation()}>
          <ToolToggle enabled={tool.isEnabled} onToggle={() => toggleTool(tool.name)} />
        </div>

        {/* Expand chevron */}
        <div className="text-foreground-subtle flex items-center justify-center">
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </div>
      </div>

      {/* Expanded schema section */}
      <div
        className={cn(
          'overflow-hidden transition-all duration-300 ease-in-out',
          expanded ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0'
        )}
      >
        <div className="px-4 pb-3 border-t border-border">
          <div className="flex items-center justify-between py-2">
            <span className="text-xs font-medium text-foreground-muted">{t('tool.schema')}</span>
            <button
              onClick={handleCopySchema}
              className={cn(
                'flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium transition-colors',
                copied
                  ? 'bg-success/20 text-success'
                  : 'bg-surface-hover text-foreground-muted hover:text-foreground hover:bg-surface-elevated'
              )}
            >
              {copied ? (
                <>
                  <Check className="w-3 h-3" />
                  {t('tool.copySchemaDone')}
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  {t('tool.copySchema')}
                </>
              )}
            </button>
          </div>
          <pre
            ref={schemaRef}
            className="bg-[#0f0f0f] border border-border rounded-md p-3 overflow-x-auto text-[11px] leading-relaxed text-foreground-muted font-mono max-h-64 overflow-y-auto"
          >
            {JSON.stringify(tool.schema, null, 2)}
          </pre>
          {/* Tool metadata */}
          <div className="flex flex-wrap gap-3 mt-2 text-[10px] text-foreground-subtle">
            <span className="flex items-center gap-1">
              <span className="text-foreground-muted">{t('tool.capabilities')}:</span>
              <span>{tool.capabilities.join(', ') || 'none'}</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="text-foreground-muted">{t('tool.parallel')}:</span>
              <span>{tool.supportsParallel ? t('tool.yes') : t('tool.no')}</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="text-foreground-muted">{t('tool.readonly')}:</span>
              <span>{tool.isReadOnly ? t('tool.yes') : t('tool.no')}</span>
            </span>
            {tool.lastUsed && (
              <span className="flex items-center gap-1">
                <span className="text-foreground-muted">Last used:</span>
                <span>{new Date(tool.lastUsed).toLocaleString()}</span>
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
