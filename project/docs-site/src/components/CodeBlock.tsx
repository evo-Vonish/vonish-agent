import { useState, useEffect } from 'react';
import Prism from 'prismjs';
import 'prismjs/components/prism-typescript';
import 'prismjs/components/prism-javascript';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-bash';
import 'prismjs/components/prism-json';
import 'prismjs/components/prism-yaml';
import 'prismjs/components/prism-css';
import 'prismjs/components/prism-jsx';
import 'prismjs/components/prism-tsx';
import 'prismjs/components/prism-markdown';
import 'prismjs/components/prism-docker';
import { Copy, Check } from 'lucide-react';

interface CodeBlockProps {
  code: string;
  language?: string;
}

const languageMap: Record<string, string> = {
  'ts': 'typescript',
  'tsx': 'tsx',
  'js': 'javascript',
  'jsx': 'jsx',
  'py': 'python',
  'python': 'python',
  'bash': 'bash',
  'sh': 'bash',
  'shell': 'bash',
  'json': 'json',
  'yaml': 'yaml',
  'yml': 'yaml',
  'css': 'css',
  'md': 'markdown',
  'docker': 'docker',
  'dockerfile': 'docker',
};

export default function CodeBlock({ code, language = 'text' }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const mappedLang = languageMap[language] || language || 'text';

  useEffect(() => {
    Prism.highlightAll();
  }, [code, language]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative group my-4">
      <div className="flex items-center justify-between px-4 py-2 bg-[#1a1a1a] border border-b-0 border-border rounded-t-lg">
        <span className="text-xs text-text-dim font-mono uppercase">{language}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2 py-1 text-xs text-text-dim hover:text-text 
                     bg-surface hover:bg-surface-hover rounded transition-colors"
          title="复制代码"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-green-400" />
              <span className="text-green-400">已复制</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span>复制</span>
            </>
          )}
        </button>
      </div>
      <pre className="!mt-0 !rounded-t-none !bg-[#0f0f0f] !border-border">
        <code className={`language-${mappedLang} text-[13px] leading-relaxed`}>
          {code}
        </code>
      </pre>
    </div>
  );
}
