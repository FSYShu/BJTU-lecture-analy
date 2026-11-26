import { useContext, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Transformer } from 'markmap-lib';
import { Markmap } from 'markmap-view';
import type { Mindmap } from '@/types';
import { SeekContext } from '@/components/Player';

interface MindmapProps {
  mindmap: Mindmap;
  onSeek?: (t: number) => void;
}

export default function MindmapView({ mindmap, onSeek }: MindmapProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const mmRef = useRef<Markmap | null>(null);
  const onSeekRef = useRef(onSeek);
  const seek = useContext(SeekContext) ?? onSeek;
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    onSeekRef.current = seek;
  }, [seek]);

  const md = buildMarkdown(mindmap);

  useEffect(() => {
    if (!svgRef.current) return;
    const { root } = new Transformer().transform(md);

    if (!mmRef.current) {
      mmRef.current = Markmap.create(svgRef.current, undefined, root);
    } else {
      mmRef.current.setData(root);
    }

    return () => {
      mmRef.current?.destroy();
      mmRef.current = null;
    };
  }, [md]);

  useEffect(() => {
    if (isFullscreen && mmRef.current) {
      requestAnimationFrame(() => {
        mmRef.current?.fit();
      });
    }
  }, [isFullscreen]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onClick = (ev: MouseEvent) => {
      const target = ev.target as HTMLElement | null;
      const el = target?.closest?.('[data-t]');
      if (el) {
        const t = parseFloat(el.getAttribute('data-t') || '');
        if (!Number.isNaN(t)) onSeekRef.current?.(t);
      }
    };
    svg.addEventListener('click', onClick);
    return () => svg.removeEventListener('click', onClick);
  }, []);

  return (
    <>
      <div className="border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800">
        <div className="flex items-center justify-between px-4 py-2 border-b dark:border-gray-700">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">思维导图</span>
            {mindmap.ai_generated && <span className="text-[10px] text-accent-500 dark:text-accent-200 bg-accent-50 dark:bg-accent-700/30 px-1 rounded">AI</span>}
          </div>
          <button
              onClick={() => setIsFullscreen(true)}
              className="text-gray-400 dark:text-gray-500 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
              title="全屏显示"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3" />
              </svg>
            </button>

        </div>
        <div className="p-2">
          <svg ref={svgRef} className="w-full h-[32rem]" />
        </div>
      </div>

      {isFullscreen && createPortal(
        <div className="fixed inset-0 z-[100] bg-black/50 flex items-center justify-center p-4" onClick={() => setIsFullscreen(false)}>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-[90vw] h-[80vh] flex flex-col overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-2">
                <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100">思维导图</h3>
                {mindmap.ai_generated && <span className="text-[10px] text-accent-500 dark:text-accent-200 bg-accent-50 dark:bg-accent-700/30 px-1 rounded">AI</span>}
              </div>
              <button
                onClick={() => setIsFullscreen(false)}
                className="text-gray-400 dark:text-gray-500 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
                title="关闭"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 p-4 overflow-hidden">
              <FullscreenMindmap mindmap={mindmap} seek={seek ?? (() => {})} />
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}

function FullscreenMindmap({ mindmap, seek }: { mindmap: Mindmap; seek: (t: number) => void }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const mmRef = useRef<Markmap | null>(null);
  const md = buildMarkdown(mindmap);

  useEffect(() => {
    if (!svgRef.current) return;
    const { root } = new Transformer().transform(md);
    mmRef.current = Markmap.create(svgRef.current, undefined, root);
    requestAnimationFrame(() => mmRef.current?.fit());

    return () => {
      mmRef.current?.destroy();
      mmRef.current = null;
    };
  }, [md]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onClick = (ev: MouseEvent) => {
      const target = ev.target as HTMLElement | null;
      const el = target?.closest?.('[data-t]');
      if (el) {
        const t = parseFloat(el.getAttribute('data-t') || '');
        if (!Number.isNaN(t)) seek(t);
      }
    };
    svg.addEventListener('click', onClick);
    return () => svg.removeEventListener('click', onClick);
  }, [seek]);

  return <svg ref={svgRef} className="w-full h-full" />;
}

function buildMarkdown(m: Mindmap): string {
  let nodes: any[] = [];
  try { nodes = JSON.parse(m.nodes); } catch { /* 容错 */ }
  let md = `# ${m.root_topic}\n`;
  for (const mod of nodes) {
    md += `## ${mod.module}\n`;
    for (const kp of mod.knowledge_points || []) {
      const name = String(kp.name ?? '');
      md += kp.timestamp_sec != null
        ? `- <span data-t="${kp.timestamp_sec}">${name}</span>\n`
        : `- ${name}\n`;
    }
  }
  return md;
}
