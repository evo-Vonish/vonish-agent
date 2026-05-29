import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import CodeBlock from './CodeBlock';
import Breadcrumb from './Breadcrumb';

interface ContentProps {
  title: string;
  content: string;
  currentPath: string;
}

// Custom renderer for code blocks
const CodeComponent = ({ node, inline, className, children, ...props }: any) => {
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : '';
  const code = String(children).replace(/\n$/, '');

  if (inline || !language) {
    return (
      <code className={className} {...props}>
        {children}
      </code>
    );
  }

  return <CodeBlock code={code} language={language} />;
};

// Custom renderer for pre blocks (prevent double wrapping)
const PreComponent = ({ children }: any) => {
  return <>{children}</>;
};

// Custom heading renderer with anchor IDs
const createHeadingComponent = (level: number) => {
  return ({ children }: any) => {
    const text = typeof children === 'string' ? children : 
      Array.isArray(children) ? children.join('') : '';
    const id = text.toLowerCase()
      .replace(/[^\w\s-]/g, '')
      .replace(/\s+/g, '-')
      .substring(0, 50);
    
    const Tag = `h${level}` as keyof JSX.IntrinsicElements;
    const className = level === 1 ? 'doc-h1' : level === 2 ? 'doc-h2' : level === 3 ? 'doc-h3' : 'doc-h4';
    
    return (
      <Tag id={id} className={className}>
        {children}
      </Tag>
    );
  };
};

export default function Content({ title, content, currentPath }: ContentProps) {
  return (
    <div className="max-w-4xl mx-auto">
      <Breadcrumb currentPath={currentPath} />
      
      <article className="doc-content pb-20">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            code: CodeComponent,
            pre: PreComponent,
            h1: createHeadingComponent(1),
            h2: createHeadingComponent(2),
            h3: createHeadingComponent(3),
            h4: createHeadingComponent(4),
          }}
        >
          {content}
        </ReactMarkdown>
      </article>
    </div>
  );
}
