import type { ReactNode } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useLanguageStore } from '@/stores/languageStore';
import { useSettingsStore, type AutoSaveMode } from '@/stores/settingsStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useWorkbenchStore } from '@/stores/workbenchStore';
import type { Locale } from '@/i18n/types';

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[#5c5855]">{title}</h3>
      <div className="space-y-2 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">{children}</div>
    </section>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="text-[13px] text-[#e8e6e3]">{label}</div>
        {hint && <div className="text-[11px] text-[#5c5855]">{hint}</div>}
      </div>
      {children}
    </div>
  );
}

function Capability({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="flex items-start gap-2">
      <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#5a8a5e]" />
      <div>
        <div className="text-[12.5px] text-[#e8e6e3]">{label}</div>
        <div className="text-[11px] text-[#5c5855]">{detail}</div>
      </div>
    </div>
  );
}

const LOCALES: { id: Locale; label: string }[] = [
  { id: 'en-US', label: 'English' },
  { id: 'zh-CN', label: '简体中文' },
  { id: 'ja-JP', label: '日本語' },
  { id: 'ko-KR', label: '한국어' },
  { id: 'fr-FR', label: 'Français' },
  { id: 'de-DE', label: 'Deutsch' },
];

const AUTO_SAVE: { id: AutoSaveMode; label: string }[] = [
  { id: 'off', label: '关闭' },
  { id: 'delay', label: '延时自动保存' },
  { id: 'blur', label: '失焦时保存' },
];

const selectClass = 'rounded-md border border-white/10 bg-[#161618] px-2 py-1 text-[12px] text-[#e8e6e3] outline-none';

export function SettingsTab() {
  const locale = useLanguageStore((s) => s.locale);
  const setLocale = useLanguageStore((s) => s.setLocale);
  const autoSave = useSettingsStore((s) => s.autoSave);
  const setAutoSave = useSettingsStore((s) => s.setAutoSave);
  const gitStatus = useWorkspaceStore((s) => s.gitStatus);
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspaceId);
  const setActiveTab = useWorkbenchStore((s) => s.setActiveTab);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="mx-auto max-w-[560px] space-y-5">
        <Section title="Appearance">
          <Row label="主题" hint="深色工程风格（VS Code-like），当前唯一主题。">
            <span className="rounded-md bg-white/[0.05] px-2 py-1 text-[12px] text-[#9a9590]">Dark</span>
          </Row>
        </Section>

        <Section title="Language">
          <Row label="界面语言" hint="Interface language">
            <select className={selectClass} value={locale} onChange={(e) => setLocale(e.target.value as Locale)}>
              {LOCALES.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
            </select>
          </Row>
        </Section>

        <Section title="File Workbench">
          <Row label="自动保存" hint="Auto Save — 编辑文本/代码文件时">
            <select className={selectClass} value={autoSave} onChange={(e) => setAutoSave(e.target.value as AutoSaveMode)}>
              {AUTO_SAVE.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </Row>
          <Row label="编辑器" hint="CodeMirror 6 · 语法高亮 · 行号 · 选区引用" />
        </Section>

        <Section title="Workspace">
          <Row label="当前 Workspace" hint={activeWorkspaceId || '未选择'}>
            <span className={cn('rounded-md px-2 py-1 text-[12px]', gitStatus?.is_git_repo ? 'bg-[#5a8a5e]/15 text-[#7ec98a]' : 'bg-white/[0.05] text-[#9a9590]')}>
              {gitStatus?.is_git_repo ? `git: ${gitStatus.branch || 'repo'}` : 'no git'}
            </span>
          </Row>
        </Section>

        <Section title="Capabilities / 能力状态">
          <Capability label="Office 预览" detail="服务端转换：python-docx / openpyxl / python-pptx → 结构化预览 + 引用" />
          <Capability label="PDF 预览" detail="服务端 PyMuPDF：分页图像渲染 + 文本块选择 + 引用" />
          <Capability label="HTML 渲染" detail="沙箱 iframe：元素悬停高亮 + 点击选择 + 引用" />
          <Capability label="引用系统" detail="文本/代码/HTML/Office/PDF/AI 回复 → 统一引用并随消息发送至 Agent" />
          <Capability label="提议编辑" detail="AI 修改以 Apply / Reject 呈现，不会静默写入文件" />
        </Section>

        <Section title="Model / API / Permissions">
          <Row label="模型、API Key 与上下文档位" hint="在 State 面板的 Config 标签中管理">
            <button onClick={() => setActiveTab('state')} className="rounded-md border border-white/10 px-2 py-1 text-[12px] text-[#e8e6e3] transition-colors hover:bg-white/[0.08]">
              打开 State · Config
            </button>
          </Row>
        </Section>

        <div className="pt-2 text-[10.5px] leading-4 text-[#5c5855]">
          Browser Runtime、Artifact Renderers 等更多设置将随对应功能逐步迁移到此处。
        </div>
      </div>
    </div>
  );
}
