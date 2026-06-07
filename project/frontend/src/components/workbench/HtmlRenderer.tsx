import { useEffect, useMemo, useRef, useState } from 'react';
import { Code2, Eye, MessageSquareQuote, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { popoverPosition } from '@/lib/selectionRef';
import { useInlinePromptStore } from '@/stores/inlinePromptStore';
import { useReferenceStore, type NewReference } from '@/stores/referenceStore';
import { useWorkbenchStore, type WorkbenchTab } from '@/stores/workbenchStore';
import { CodeEditor } from './CodeEditor';

interface ElementInfo {
  tagName: string;
  id: string;
  className: string;
  cssPath: string;
  text: string;
  outerHTML: string;
  rect: { left: number; top: number; bottom: number; right: number; width: number; height: number };
}

// Injected into the sandboxed preview iframe: hover outline + click-to-select,
// posts the selected element's metadata to the parent, and honours reveal requests.
const INJECT = [
  '<script>(function(){',
  'var hovered=null,selected=null;',
  'var s=document.createElement("style");',
  's.textContent=".__wbhover{outline:2px solid rgba(198,106,56,.6)!important;outline-offset:-2px!important;cursor:pointer!important;}.__wbsel{outline:2px solid rgba(198,106,56,.95)!important;outline-offset:-2px!important;}";',
  'document.documentElement.appendChild(s);',
  'function cssPath(el){if(!el||el.nodeType!==1)return"";var p=[];while(el&&el.nodeType===1&&p.length<6){var sel=el.nodeName.toLowerCase();if(el.id){p.unshift("#"+el.id);break;}var c=(el.className&&el.className.toString)?el.className.toString().trim().split(/\\s+/).filter(Boolean).slice(0,2).join("."):"";if(c)sel+="."+c;var par=el.parentNode;if(par&&par.children){var same=[].filter.call(par.children,function(x){return x.nodeName===el.nodeName;});if(same.length>1){var i=[].indexOf.call(par.children,el)+1;sel+=":nth-child("+i+")";}}p.unshift(sel);el=el.parentNode;}return p.join(" > ");}',
  'document.addEventListener("mouseover",function(e){if(hovered&&hovered.classList)hovered.classList.remove("__wbhover");hovered=e.target;if(hovered&&hovered.classList)hovered.classList.add("__wbhover");},true);',
  'document.addEventListener("mouseout",function(e){if(e.target&&e.target.classList)e.target.classList.remove("__wbhover");},true);',
  'document.addEventListener("click",function(e){e.preventDefault();e.stopPropagation();var el=e.target;if(!el||el.nodeType!==1)return;if(selected&&selected.classList)selected.classList.remove("__wbsel");selected=el;el.classList.add("__wbsel");var r=el.getBoundingClientRect();parent.postMessage({__wb_html_select:true,info:{tagName:el.nodeName.toLowerCase(),id:el.id||"",className:(el.className&&el.className.toString)?el.className.toString():"",cssPath:cssPath(el),text:(el.innerText||el.textContent||"").slice(0,200),outerHTML:(el.outerHTML||"").slice(0,400),rect:{left:r.left,top:r.top,bottom:r.bottom,right:r.right,width:r.width,height:r.height}}},"*");},true);',
  'window.addEventListener("message",function(e){var d=e.data;if(!d||!d.__wb_reveal)return;try{var t=d.cssPath?document.querySelector(d.cssPath):(d.elementId?document.getElementById(d.elementId):null);if(t){if(selected&&selected.classList)selected.classList.remove("__wbsel");selected=t;t.classList.add("__wbsel");t.scrollIntoView({behavior:"smooth",block:"center"});}}catch(_){}});',
  '})();</script>',
].join('');

export function HtmlRenderer({ tab }: { tab: WorkbenchTab }) {
  const [mode, setMode] = useState<'rendered' | 'source'>('rendered');
  const [selected, setSelected] = useState<ElementInfo | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const updateContent = useWorkbenchStore((s) => s.updateContent);
  const addReference = useReferenceStore((s) => s.addReference);
  const openPrompt = useInlinePromptStore((s) => s.openPrompt);
  const reveal = useWorkbenchStore((s) => (s.reveal && s.reveal.tabId === tab.id ? s.reveal : null));

  const srcDoc = useMemo(() => {
    const html = tab.content ?? '';
    return html.includes('</body>') ? html.replace('</body>', `${INJECT}</body>`) : html + INJECT;
  }, [tab.content]);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const data = event.data;
      if (data && data.__wb_html_select && data.info) setSelected(data.info as ElementInfo);
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, []);

  // Jump-back: switch to rendered mode and ask the iframe to highlight the element.
  useEffect(() => {
    if (!reveal || (!reveal.cssPath && !reveal.elementId)) return;
    setMode('rendered');
    const timer = window.setTimeout(() => {
      iframeRef.current?.contentWindow?.postMessage(
        { __wb_reveal: true, cssPath: reveal.cssPath, elementId: reveal.elementId },
        '*',
      );
    }, 320);
    return () => window.clearTimeout(timer);
  }, [reveal]);

  const buildDraft = (info: ElementInfo): NewReference => {
    const suffix = info.id ? `#${info.id}` : info.className ? `.${info.className.split(' ')[0]}` : '';
    return {
      sourceType: 'html-element',
      title: `${tab.title} · ${info.tagName}${suffix}`,
      preview: `<${info.tagName}${info.id ? ` id="${info.id}"` : ''}${info.className ? ` class="${info.className}"` : ''}>\n${info.text}`.trim(),
      location: {
        filePath: tab.path,
        workspaceId: tab.workspaceId ?? undefined,
        elementId: info.id || undefined,
        cssPath: info.cssPath,
        tagName: info.tagName,
      },
      payload: { outerHTML: info.outerHTML },
    };
  };

  const actionPos = () => {
    const frame = iframeRef.current?.getBoundingClientRect();
    if (!frame || !selected) return { left: 16, top: 16 };
    const r = selected.rect;
    return popoverPosition({ left: frame.left + r.left, top: frame.top + r.top, bottom: frame.top + r.bottom }, 200, 40);
  };

  const pos = selected ? actionPos() : { left: 0, top: 0 };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-1 border-b border-white/[0.06] px-3 py-1.5">
        {(['rendered', 'source'] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={cn(
              'flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11.5px] transition-colors',
              mode === m ? 'bg-white/[0.07] text-[#e8e6e3]' : 'text-[#5c5855] hover:text-[#9a9590]',
            )}
          >
            {m === 'rendered' ? <Eye className="h-3.5 w-3.5" /> : <Code2 className="h-3.5 w-3.5" />}
            {m === 'rendered' ? 'Rendered' : 'Source'}
          </button>
        ))}
        {mode === 'rendered' && <span className="ml-2 text-[10.5px] text-[#5c5855]">悬停高亮 · 点击元素以选择</span>}
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden">
        {mode === 'rendered' ? (
          <iframe
            ref={iframeRef}
            title={tab.title}
            sandbox="allow-scripts"
            srcDoc={srcDoc}
            className="h-full w-full border-0 bg-white"
          />
        ) : (
          <CodeEditor
            value={tab.content ?? ''}
            language="html"
            readOnly={tab.readonly}
            onChange={(value) => updateContent(tab.id, value)}
            quoteSource={tab.path ? { filePath: tab.path, title: tab.title, workspaceId: tab.workspaceId } : undefined}
          />
        )}

        {mode === 'rendered' && selected && (
          <div
            className="fixed z-[70] flex items-center gap-1 rounded-lg border border-white/[0.12] bg-[#1d1d1d] p-1 shadow-[0_10px_30px_rgba(0,0,0,0.45)]"
            style={{ left: pos.left, top: pos.top }}
          >
            <span className="px-1.5 font-mono-code text-[10.5px] text-[#9a9590]">
              {selected.tagName}{selected.id ? `#${selected.id}` : ''}
            </span>
            <button
              onClick={() => { addReference(buildDraft(selected)); setSelected(null); }}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-[#e8e6e3] transition-colors hover:bg-white/[0.08]"
            >
              <MessageSquareQuote className="h-3.5 w-3.5" /> 引用
            </button>
            <button
              onClick={() => { openPrompt(buildDraft(selected), actionPos()); setSelected(null); }}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-[#e8e6e3] transition-colors hover:bg-white/[0.08]"
            >
              <Sparkles className="h-3.5 w-3.5 text-[#c66a38]" /> 问 AI
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
