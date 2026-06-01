import TurndownService from 'turndown';

/**
 * Convert HTML to Markdown with content-preserving rules.
 *
 * Features:
 *   - Table preservation
 *   - Image lazy-loading support (data-src → src fallback)
 *   - Relative URL → absolute URL resolution
 *   - ATX headings
 *   - Fenced code blocks
 */
export function buildMarkdown(html: string, baseUrl: string): string {
  const turndown = new TurndownService({
    headingStyle: 'atx',
    bulletListMarker: '-',
    codeBlockStyle: 'fenced',
    hr: '---',
    emDelimiter: '*',
  });

  // Table cell rule — preserve table formatting
  turndown.addRule('tableCell', {
    filter: ['th', 'td'],
    replacement: (content: string) => {
      return ` ${content.trim()} |`;
    },
  });

  // Table row rule
  turndown.addRule('tableRow', {
    filter: 'tr',
    replacement: (content: string) => {
      return `|${content}\n`;
    },
  });

  // Image rule — handle lazy loading (data-src attribute)
  turndown.addRule('image', {
    filter: 'img',
    replacement: (_content: string, node: any) => {
      const el = node as HTMLElement;
      if (!el || !el.getAttribute) return '';

      const src = el.getAttribute('data-src')
        || el.getAttribute('data-lazy-src')
        || el.getAttribute('data-original')
        || el.getAttribute('src')
        || '';

      const alt = el.getAttribute('alt') || '';

      if (!src) return '';

      // Resolve relative URLs
      let absoluteSrc = src;
      if (baseUrl && !src.startsWith('http') && !src.startsWith('data:')) {
        try {
          absoluteSrc = new URL(src, baseUrl).href;
        } catch {
          // Keep original if resolution fails
        }
      }

      return `![${alt}](${absoluteSrc})`;
    },
  });

  // Link rule — resolve relative URLs
  turndown.addRule('link', {
    filter: 'a',
    replacement: (content: string, node: any) => {
      const el = node as HTMLElement;
      if (!el || !el.getAttribute) return content;

      const href = el.getAttribute('href') || '';
      if (!href) return content;

      let absoluteHref = href;
      if (baseUrl && !href.startsWith('http') && !href.startsWith('#') && !href.startsWith('mailto:') && !href.startsWith('javascript:')) {
        try {
          absoluteHref = new URL(href, baseUrl).href;
        } catch {
          // Keep original
        }
      }

      return `[${content}](${absoluteHref})`;
    },
  });

  // Pre/code rule — preserve code blocks
  turndown.addRule('preCode', {
    filter: (node: any) => {
      return node.nodeName === 'PRE' && node.firstChild?.nodeName === 'CODE';
    },
    replacement: (_content: string, node: any) => {
      const code = node.firstChild;
      const text = code.textContent || '';
      const language = code.getAttribute?.('class')?.replace('language-', '') || '';
      return `\n\`\`\`${language}\n${text}\n\`\`\`\n`;
    },
  });

  return turndown.turndown(html);
}
