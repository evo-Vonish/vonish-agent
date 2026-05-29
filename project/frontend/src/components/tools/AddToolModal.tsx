import { useState, useRef, useEffect } from 'react';
import { X, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ToolDefinition, ToolCategoryType, ApprovalLevel, ToolCapability } from '@/types/tools';
import { useToolStore } from '@/stores/useToolStore';
import { generateId } from '@/lib/utils';

interface AddToolModalProps {
  open: boolean;
  onClose: () => void;
}

const CATEGORIES: { value: ToolCategoryType; label: string }[] = [
  { value: 'file_ops', label: 'File Operations' },
  { value: 'workspace', label: 'Workspace' },
  { value: 'web_search', label: 'Web Search' },
  { value: 'system', label: 'System' },
];

const APPROVAL_LEVELS: { value: ApprovalLevel; label: string }[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'suggest', label: 'Suggest' },
  { value: 'required', label: 'Required' },
];

const CAPABILITIES: { value: ToolCapability; label: string }[] = [
  { value: 'read_only', label: 'Read Only' },
  { value: 'writes_files', label: 'Writes Files' },
  { value: 'requires_approval', label: 'Requires Approval' },
];

export function AddToolModal({ open, onClose }: AddToolModalProps) {
  const addTool = useToolStore((s) => s.addTool);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState<ToolCategoryType>('file_ops');
  const [approvalLevel, setApprovalLevel] = useState<ApprovalLevel>('suggest');
  const [capabilities, setCapabilities] = useState<ToolCapability[]>([]);
  const [schemaText, setSchemaText] = useState('{\n  "type": "object",\n  "properties": {}\n}');
  const [error, setError] = useState('');
  const [supportsParallel, setSupportsParallel] = useState(false);

  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setTimeout(() => nameInputRef.current?.focus(), 100);
    }
  }, [open]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (open) {
      window.addEventListener('keydown', handleEsc);
      return () => window.removeEventListener('keydown', handleEsc);
    }
  }, [open, onClose]);

  const toggleCapability = (cap: ToolCapability) => {
    setCapabilities((prev) =>
      prev.includes(cap) ? prev.filter((c) => c !== cap) : [...prev, cap]
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!name.trim()) {
      setError('Tool name is required');
      return;
    }
    if (!description.trim()) {
      setError('Description is required');
      return;
    }

    let schema: Record<string, unknown> = {};
    try {
      schema = JSON.parse(schemaText);
    } catch {
      setError('Invalid JSON Schema');
      return;
    }

    const existingTool = useToolStore.getState().getToolByName(name.trim());
    if (existingTool) {
      setError(`Tool "${name}" already exists`);
      return;
    }

    const newTool: ToolDefinition = {
      name: name.trim(),
      description: description.trim(),
      category,
      capabilities,
      approvalLevel,
      isEnabled: true,
      isReadOnly: capabilities.includes('read_only') && !capabilities.includes('writes_files'),
      supportsParallel,
      schema,
      useCount: 0,
    };

    addTool(newTool);
    resetForm();
    onClose();
  };

  const resetForm = () => {
    setName('');
    setDescription('');
    setCategory('file_ops');
    setApprovalLevel('suggest');
    setCapabilities([]);
    setSchemaText('{\n  "type": "object",\n  "properties": {}\n}');
    setError('');
    setSupportsParallel(false);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg mx-4 bg-surface border border-border rounded-xl shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-base font-semibold text-foreground">Add New Tool</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-surface-hover text-foreground-muted hover:text-foreground transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-5 space-y-4">
          {error && (
            <div className="px-3 py-2 rounded-md bg-error/10 border border-error/30 text-error text-xs">
              {error}
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">Tool Name</label>
            <input
              ref={nameInputRef}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. my_custom_tool"
              className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border text-foreground placeholder:text-foreground-subtle focus:outline-none focus:border-primary/50 transition-colors"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What does this tool do?"
              className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border text-foreground placeholder:text-foreground-subtle focus:outline-none focus:border-primary/50 transition-colors"
            />
          </div>

          {/* Category */}
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">Category</label>
            <div className="grid grid-cols-2 gap-2">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat.value}
                  type="button"
                  onClick={() => setCategory(cat.value)}
                  className={cn(
                    'px-3 py-2 text-xs rounded-md border transition-colors text-left',
                    category === cat.value
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border bg-background text-foreground-muted hover:border-border-hover hover:text-foreground'
                  )}
                >
                  {cat.label}
                </button>
              ))}
            </div>
          </div>

          {/* Approval Level */}
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">Approval Level</label>
            <div className="flex gap-2">
              {APPROVAL_LEVELS.map((level) => (
                <button
                  key={level.value}
                  type="button"
                  onClick={() => setApprovalLevel(level.value)}
                  className={cn(
                    'flex-1 px-3 py-2 text-xs rounded-md border transition-colors',
                    approvalLevel === level.value
                      ? level.value === 'auto'
                        ? 'border-success bg-success/10 text-success'
                        : level.value === 'suggest'
                          ? 'border-warning bg-warning/10 text-warning'
                          : 'border-error bg-error/10 text-error'
                      : 'border-border bg-background text-foreground-muted hover:border-border-hover hover:text-foreground'
                  )}
                >
                  {level.label}
                </button>
              ))}
            </div>
          </div>

          {/* Capabilities */}
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">Capabilities</label>
            <div className="flex flex-wrap gap-2">
              {CAPABILITIES.map((cap) => (
                <button
                  key={cap.value}
                  type="button"
                  onClick={() => toggleCapability(cap.value)}
                  className={cn(
                    'px-3 py-1.5 text-xs rounded-md border transition-colors',
                    capabilities.includes(cap.value)
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border bg-background text-foreground-muted hover:border-border-hover'
                  )}
                >
                  {cap.label}
                </button>
              ))}
            </div>
          </div>

          {/* Supports Parallel */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSupportsParallel(!supportsParallel)}
              className={cn(
                'w-4 h-4 rounded border flex items-center justify-center transition-colors',
                supportsParallel
                  ? 'bg-primary border-primary'
                  : 'border-border bg-background'
              )}
            >
              {supportsParallel && (
                <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              )}
            </button>
            <span className="text-xs text-foreground-muted">Supports parallel execution</span>
          </div>

          {/* Schema */}
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">JSON Schema</label>
            <textarea
              value={schemaText}
              onChange={(e) => setSchemaText(e.target.value)}
              rows={6}
              className="w-full px-3 py-2 text-xs rounded-md bg-[#0f0f0f] border border-border text-foreground-muted font-mono focus:outline-none focus:border-primary/50 transition-colors resize-none"
            />
          </div>
        </form>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium rounded-md border border-border text-foreground-muted hover:text-foreground hover:bg-surface-hover transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-md bg-primary text-white hover:bg-primary-hover transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Tool
          </button>
        </div>
      </div>
    </div>
  );
}
