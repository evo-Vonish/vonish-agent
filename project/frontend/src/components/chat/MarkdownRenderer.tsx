import { useMemo } from 'react';
import { cn } from '@/lib/utils';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

// Simple markdown parser without external deps
function parseMarkdown(text: string): string {
  if (!text) return '';

  let html = text
    // Escape HTML
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // Code blocks
    .replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
      const langClass = lang ? ` class="language-${lang}"` : '';
      return `<pre class="code-block"><code${langClass}>${code.trim()}</code></pre>`;
    })
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
    // Headers
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    // Bold & Italic
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Strikethrough
    .replace(/~~(.+?)~~/g, '<del>$1</del>')
    // Blockquote
    .replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>')
    // Unordered list
    .replace(/^\s*[-*+]\s+(.+$)/gim, '<li class="ul-item">$1</li>')
    // Ordered list
    .replace(/^\s*(\d+)\.\s+(.+$)/gim, '<li class="ol-item" data-num="$1">$2</li>')
    // Checkbox list
    .replace(/^\s*\[x\]\s+(.+$)/gim, '<li class="check-item checked">$1</li>')
    .replace(/^\s*\[ \]\s+(.+$)/gim, '<li class="check-item">$1</li>')
    // Links
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    // Images
    .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" />')
    // Tables (simple)
    .replace(/\|(.+)\|/g, (match) => {
      if (match.includes('---')) return '';
      const cells = match.split('|').filter(Boolean).map(c => c.trim());
      return '<tr>' + cells.map(c => `<td>${c}</td>`).join('') + '</tr>';
    })
    // Horizontal rule
    .replace(/^---+$/gim, '<hr />')
    // Line breaks
    .replace(/\n/g, '<br />');

  // Wrap table rows
  if (html.includes('<tr>')) {
    html = html.replace(/(<tr>.*?<\/tr>)/g, '<table class="md-table">$1</table>');
  }

  return html;
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  const html = useMemo(() => parseMarkdown(content), [content]);

  return (
    <div
      className={cn(
        'markdown-body prose prose-invert prose-sm max-w-none',
        'text-foreground leading-relaxed',
        className
      )}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
