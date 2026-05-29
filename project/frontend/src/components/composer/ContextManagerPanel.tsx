import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Check,
  Cpu,
  Gauge,
  KeyRound,
  Pencil,
  Plus,
  Save,
  Server,
  Trash2,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { Progress } from '@/components/ui/Progress';
import type { ContextProfile } from '@/types';
import {
  type ApiConfig,
  createApiConfig,
  deleteApiConfig,
  listApiConfigs,
  setDefaultApiConfig,
  updateApiConfig,
} from '@/services/api';

interface ContextManagerPanelProps {
  className?: string;
}

type Provider = 'deepseek' | 'kimi';
type Tab = 'api' | 'context';

const providerLabels: Record<Provider, string> = {
  deepseek: 'DeepSeek',
  kimi: 'Kimi',
};

const defaultBases: Record<Provider, string> = {
  deepseek: 'https://api.deepseek.com',
  kimi: 'https://api.moonshot.cn/v1',
};

const emptyForm = {
  id: '',
  provider: 'deepseek' as Provider,
  name: '',
  apiBase: defaultBases.deepseek,
  apiKey: '',
  isDefault: true,
};

function TokenGauge({ used, budget }: { used: number; budget: number }) {
  const pct = Math.min(100, (used / budget) * 100);
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (pct / 100) * circumference;

  const getColor = () => {
    if (pct < 50) return '#22c55e';
    if (pct < 80) return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div className="flex flex-col items-center py-3">
      <div className="relative w-28 h-28">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r={radius} fill="none" stroke="#2a2a2a" strokeWidth="8" />
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={getColor()}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            className="transition-all duration-700 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-lg font-bold text-foreground">{pct.toFixed(0)}%</span>
          <span className="text-[10px] text-foreground-muted">已使用</span>
        </div>
      </div>
      <div className="text-center mt-2">
        <span className="text-xs text-foreground-muted">
          {(used / 1000).toFixed(1)}K / {(budget / 1000).toFixed(0)}K tokens
        </span>
      </div>
    </div>
  );
}

export function ContextManagerPanel({ className }: ContextManagerPanelProps) {
  const { contextProfile, setContextProfile } = useChatStore();
  const { toggleRightPanel } = useUIStore();
  const [activeTab, setActiveTab] = useState<Tab>('api');
  const [configs, setConfigs] = useState<ApiConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState(emptyForm);

  const editing = Boolean(form.id);
  const grouped = useMemo(
    () => ({
      deepseek: configs.filter((config) => config.provider === 'deepseek'),
      kimi: configs.filter((config) => config.provider === 'kimi'),
    }),
    [configs],
  );

  const loadConfigs = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setConfigs(await listApiConfigs());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConfigs();
  }, [loadConfigs]);

  const setProvider = (provider: Provider) => {
    setForm((current) => ({
      ...current,
      provider,
      apiBase: current.apiBase === defaultBases[current.provider] ? defaultBases[provider] : current.apiBase,
    }));
  };

  const resetForm = (provider: Provider = form.provider) => {
    setForm({
      ...emptyForm,
      provider,
      apiBase: defaultBases[provider],
      name: `${providerLabels[provider]} 默认方案`,
    });
  };

  const editConfig = (config: ApiConfig) => {
    setForm({
      id: config.id,
      provider: config.provider,
      name: config.name,
      apiBase: config.apiBase,
      apiKey: '',
      isDefault: config.isDefault,
    });
  };

  const saveConfig = async () => {
    if (!form.name.trim()) {
      setError('请填写方案名称。');
      return;
    }
    if (!editing && !form.apiKey.trim()) {
      setError('请填写 API Key。');
      return;
    }

    setSaving(true);
    setError('');
    try {
      if (editing) {
        await updateApiConfig(form.id, {
          name: form.name.trim(),
          apiBase: form.apiBase.trim() || defaultBases[form.provider],
          apiKey: form.apiKey.trim() || undefined,
          isDefault: form.isDefault,
        });
      } else {
        await createApiConfig({
          provider: form.provider,
          name: form.name.trim(),
          apiBase: form.apiBase.trim() || defaultBases[form.provider],
          apiKey: form.apiKey.trim(),
          isDefault: form.isDefault,
        });
      }
      await loadConfigs();
      resetForm(form.provider);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const removeConfig = async (config: ApiConfig) => {
    if (!window.confirm(`删除方案 "${config.name}"？`)) return;
    setError('');
    try {
      await deleteApiConfig(config.id);
      await loadConfigs();
      if (form.id === config.id) resetForm(config.provider);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const markDefault = async (config: ApiConfig) => {
    setError('');
    try {
      await setDefaultApiConfig(config.id);
      await loadConfigs();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const compressionLevels: Array<{ value: ContextProfile['compressionLevel']; label: string }> = [
    { value: 'none', label: '无压缩' },
    { value: 'light', label: '轻度' },
    { value: 'medium', label: '中度' },
    { value: 'aggressive', label: '激进' },
  ];

  return (
    <div className={cn('h-full flex flex-col', className)}>
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-primary" />
          <span className="text-xs font-semibold">设置</span>
        </div>
        <button
          onClick={() => toggleRightPanel()}
          className="p-1 rounded hover:bg-surface-hover text-foreground-muted transition-colors"
          aria-label="关闭"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="flex border-b border-border px-2">
        <button
          onClick={() => setActiveTab('api')}
          className={cn(
            'flex-1 px-2 py-2 text-xs font-medium border-b-2 transition-colors',
            activeTab === 'api'
              ? 'border-primary text-foreground'
              : 'border-transparent text-foreground-muted hover:text-foreground',
          )}
        >
          API 配置
        </button>
        <button
          onClick={() => setActiveTab('context')}
          className={cn(
            'flex-1 px-2 py-2 text-xs font-medium border-b-2 transition-colors',
            activeTab === 'context'
              ? 'border-primary text-foreground'
              : 'border-transparent text-foreground-muted hover:text-foreground',
          )}
        >
          上下文
        </button>
      </div>

      {activeTab === 'api' ? (
        <div className="flex-1 overflow-y-auto p-3 space-y-4">
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-1 rounded-lg bg-background border border-border p-1">
              {(['deepseek', 'kimi'] as Provider[]).map((provider) => (
                <button
                  key={provider}
                  onClick={() => setProvider(provider)}
                  disabled={editing}
                  className={cn(
                    'px-2 py-1.5 rounded-md text-xs font-medium transition-colors',
                    form.provider === provider
                      ? 'bg-primary/15 text-primary'
                      : 'text-foreground-muted hover:bg-surface-hover hover:text-foreground',
                    editing && 'cursor-not-allowed opacity-70',
                  )}
                >
                  {providerLabels[provider]}
                </button>
              ))}
            </div>

            <label className="block space-y-1">
              <span className="text-[10px] text-foreground-subtle">方案名称</span>
              <input
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="例如：生产环境"
                className="w-full rounded-md bg-background border border-border px-2.5 py-1.5 text-xs text-foreground outline-none focus:border-primary/60"
              />
            </label>

            <label className="block space-y-1">
              <span className="text-[10px] text-foreground-subtle">API Base</span>
              <div className="relative">
                <Server className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground-subtle" />
                <input
                  value={form.apiBase}
                  onChange={(event) => setForm({ ...form, apiBase: event.target.value })}
                  className="w-full rounded-md bg-background border border-border pl-7 pr-2.5 py-1.5 text-xs text-foreground outline-none focus:border-primary/60"
                />
              </div>
            </label>

            <label className="block space-y-1">
              <span className="text-[10px] text-foreground-subtle">API Key</span>
              <div className="relative">
                <KeyRound className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground-subtle" />
                <input
                  value={form.apiKey}
                  onChange={(event) => setForm({ ...form, apiKey: event.target.value })}
                  type="password"
                  placeholder={editing ? '留空则保持当前 Key' : 'sk-...'}
                  className="w-full rounded-md bg-background border border-border pl-7 pr-2.5 py-1.5 text-xs text-foreground outline-none focus:border-primary/60"
                />
              </div>
            </label>

            <label className="flex items-center gap-2 text-xs text-foreground-muted">
              <input
                type="checkbox"
                checked={form.isDefault}
                onChange={(event) => setForm({ ...form, isDefault: event.target.checked })}
                className="accent-primary"
              />
              设为该供应商默认方案
            </label>

            {error && (
              <div className="rounded-md border border-error/30 bg-error/10 px-2.5 py-2 text-xs text-error">
                {error}
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={saveConfig}
                disabled={saving}
                className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-hover disabled:opacity-60"
              >
                <Save className="w-3.5 h-3.5" />
                {saving ? '保存中' : editing ? '保存修改' : '新增方案'}
              </button>
              <button
                onClick={() => resetForm(form.provider)}
                className="inline-flex items-center justify-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-foreground-muted hover:bg-surface-hover hover:text-foreground"
              >
                <Plus className="w-3.5 h-3.5" />
                新建
              </button>
            </div>
          </div>

          <div className="space-y-3">
            {(['deepseek', 'kimi'] as Provider[]).map((provider) => (
              <section key={provider} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-medium text-foreground">{providerLabels[provider]}</h4>
                  <span className="text-[10px] text-foreground-subtle">
                    {grouped[provider].length} 个方案
                  </span>
                </div>
                {loading && configs.length === 0 ? (
                  <div className="text-xs text-foreground-subtle px-2 py-2">加载中...</div>
                ) : grouped[provider].length === 0 ? (
                  <div className="rounded-md border border-border bg-background px-2.5 py-2 text-xs text-foreground-subtle">
                    暂无方案
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    {grouped[provider].map((config) => (
                      <div
                        key={config.id}
                        className="rounded-md border border-border bg-background px-2.5 py-2"
                      >
                        <div className="flex items-start gap-2">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <span className="truncate text-xs font-medium text-foreground">
                                {config.name}
                              </span>
                              {config.isDefault && (
                                <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[10px] text-primary">
                                  默认
                                </span>
                              )}
                            </div>
                            <div className="mt-1 truncate text-[10px] text-foreground-subtle">
                              {config.apiBase}
                            </div>
                            <div className="mt-0.5 text-[10px] text-foreground-subtle">
                              {config.keyPreview}
                            </div>
                          </div>
                          <div className="flex items-center gap-1">
                            {!config.isDefault && (
                              <button
                                onClick={() => markDefault(config)}
                                className="p-1 rounded hover:bg-surface-hover text-foreground-muted hover:text-primary"
                                aria-label="设为默认"
                              >
                                <Check className="w-3.5 h-3.5" />
                              </button>
                            )}
                            <button
                              onClick={() => editConfig(config)}
                              className="p-1 rounded hover:bg-surface-hover text-foreground-muted hover:text-foreground"
                              aria-label="编辑"
                            >
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => removeConfig(config)}
                              className="p-1 rounded hover:bg-error/15 text-foreground-muted hover:text-error"
                              aria-label="删除"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-3 space-y-4">
          <div className="flex items-center gap-2 text-xs text-foreground-muted">
            <Gauge className="w-4 h-4 text-primary" />
            <span>
              Profile: <span className="text-foreground font-medium">{contextProfile.name}</span>
            </span>
          </div>

          <div className="bg-surface-hover rounded-lg">
            <TokenGauge used={contextProfile.tokenUsed} budget={contextProfile.tokenBudget} />
          </div>

          <Progress
            value={contextProfile.tokenUsed}
            max={contextProfile.tokenBudget}
            label="Token 占用"
            size="sm"
            variant={contextProfile.tokenUsed / contextProfile.tokenBudget > 0.8 ? 'warning' : 'default'}
          />

          <div>
            <h4 className="text-xs font-medium text-foreground-muted mb-2">压缩档位</h4>
            <div className="grid grid-cols-2 gap-1.5">
              {compressionLevels.map((level) => (
                <button
                  key={level.value}
                  onClick={() =>
                    setContextProfile({
                      ...contextProfile,
                      compressionLevel: level.value,
                    })
                  }
                  className={cn(
                    'rounded-md border px-2.5 py-1.5 text-xs transition-colors',
                    contextProfile.compressionLevel === level.value
                      ? 'border-primary/50 bg-primary/10 text-primary'
                      : 'border-border text-foreground-muted hover:bg-surface-hover hover:text-foreground',
                  )}
                >
                  {level.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
