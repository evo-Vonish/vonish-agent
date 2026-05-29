import { useState } from 'react';
import { Image, FileCode, Globe, AtSign } from 'lucide-react';
import { cn } from '@/lib/utils';

interface InputWidgetsProps {
  className?: string;
}

type WidgetType = 'image' | 'code' | 'web' | 'mention';

interface WidgetItem {
  type: WidgetType;
  icon: React.ElementType;
  label: string;
  description: string;
}

const widgets: WidgetItem[] = [
  { type: 'image', icon: Image, label: '图片', description: '上传或引用图片' },
  { type: 'code', icon: FileCode, label: '代码', description: '插入代码片段' },
  { type: 'web', icon: Globe, label: '网页', description: '引用网页内容' },
  { type: 'mention', icon: AtSign, label: '提及', description: '@ 引用文件或上下文' },
];

export function InputWidgets({ className }: InputWidgetsProps) {
  const [activeWidget, setActiveWidget] = useState<WidgetType | null>(null);

  return (
    <div className={cn('flex items-center gap-1', className)}>
      {widgets.map((w) => (
        <button
          key={w.type}
          onClick={() => setActiveWidget(activeWidget === w.type ? null : w.type)}
          title={`${w.label} - ${w.description}`}
          className={cn(
            'p-1.5 rounded-md transition-colors',
            activeWidget === w.type
              ? 'bg-primary/20 text-primary'
              : 'text-foreground-subtle hover:text-foreground hover:bg-surface-hover'
          )}
        >
          <w.icon className="w-4 h-4" />
        </button>
      ))}
    </div>
  );
}
