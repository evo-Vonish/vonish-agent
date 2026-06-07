import { Suspense, lazy } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import type { WorkbenchTab } from '@/stores/workbenchStore';
import { TextEditorRenderer } from './TextEditorRenderer';
import { MarkdownPreviewRenderer } from './MarkdownPreviewRenderer';
import { ImageRenderer } from './ImageRenderer';
import { BinaryRenderer } from './BinaryRenderer';
import { HtmlRenderer } from './HtmlRenderer';

// Artifact renderers are lazy-loaded so they stay out of the main bundle.
const PdfRenderer = lazy(() => import('./PdfRenderer').then((m) => ({ default: m.PdfRenderer })));
const DocxRenderer = lazy(() => import('./DocxRenderer').then((m) => ({ default: m.DocxRenderer })));
const XlsxRenderer = lazy(() => import('./XlsxRenderer').then((m) => ({ default: m.XlsxRenderer })));
const PptxRenderer = lazy(() => import('./PptxRenderer').then((m) => ({ default: m.PptxRenderer })));

function Loading() {
  return (
    <div className="flex h-full items-center justify-center gap-2 text-[12px] text-[#9a9590]">
      <Loader2 className="h-4 w-4 animate-spin" />
      加载渲染器…
    </div>
  );
}

/**
 * Renderer registry: routes a file tab to the right renderer by `kind` (and, for
 * Office files, by extension). Code/markdown/html/image render eagerly; the
 * heavier artifact renderers are lazy. pdf/office fall back to a real preview.
 */
export function FileRenderer({ tab }: { tab: WorkbenchTab }) {
  if (tab.loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-[12px] text-[#9a9590]">
        <Loader2 className="h-4 w-4 animate-spin" />
        加载文件…
      </div>
    );
  }
  if (tab.error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-[12px] text-[#c97a76]">
        <AlertTriangle className="h-6 w-6" />
        {tab.error}
      </div>
    );
  }

  switch (tab.kind) {
    case 'markdown':
      return <MarkdownPreviewRenderer tab={tab} />;
    case 'html':
      return <HtmlRenderer tab={tab} />;
    case 'image':
      return <ImageRenderer tab={tab} />;
    case 'pdf':
      return <Suspense fallback={<Loading />}><PdfRenderer tab={tab} /></Suspense>;
    case 'office':
      if (tab.ext === 'docx') return <Suspense fallback={<Loading />}><DocxRenderer tab={tab} /></Suspense>;
      if (tab.ext === 'xlsx') return <Suspense fallback={<Loading />}><XlsxRenderer tab={tab} /></Suspense>;
      if (tab.ext === 'pptx') return <Suspense fallback={<Loading />}><PptxRenderer tab={tab} /></Suspense>;
      return <BinaryRenderer tab={tab} />;
    case 'binary':
      return <BinaryRenderer tab={tab} />;
    case 'code':
    default:
      return <TextEditorRenderer tab={tab} />;
  }
}
