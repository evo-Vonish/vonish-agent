import { ChevronRight, Home } from 'lucide-react';
import { docs } from '@/data/docs';

interface BreadcrumbProps {
  currentPath: string;
}

export default function Breadcrumb({ currentPath }: BreadcrumbProps) {
  const pathMap: Record<string, string> = {
    '/': '首页',
    '/quickstart': '快速开始',
    '/architecture': '架构概览',
    '/agent-loop': 'Agent Loop',
    '/models': '模型适配层',
    '/tools': '工具运行时',
    '/context-os': 'Context OS',
    '/workspace': 'Workspace',
    '/frontend': '前端',
    '/api': 'API 文档',
    '/deployment': '部署',
    '/faq': '常见问题',
  };

  const label = pathMap[currentPath] || '首页';
  const docEntry = Object.values(docs).find(d => d.title === label);
  const section = docEntry ? '' : '';

  return (
    <nav className="flex items-center gap-1.5 text-sm text-text-dim mb-6">
      <button 
        onClick={() => {}}
        className="flex items-center gap-1 hover:text-text transition-colors"
      >
        <Home className="w-3.5 h-3.5" />
        <span>文档</span>
      </button>
      <ChevronRight className="w-3.5 h-3.5" />
      <span className="text-text font-medium">{label}</span>
      {section && (
        <>
          <ChevronRight className="w-3.5 h-3.5" />
          <span className="text-accent">{section}</span>
        </>
      )}
    </nav>
  );
}
