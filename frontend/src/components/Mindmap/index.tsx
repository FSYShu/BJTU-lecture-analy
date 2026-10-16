import { useEffect, useRef } from 'react';
import { Transformer } from 'markmap-lib';
import { Markmap } from 'markmap-view';
import type { Mindmap } from '@/types';

interface MindmapProps {
  mindmap: Mindmap;
  onSeek?: (t: number) => void;
}

export default function MindmapView({ mindmap, onSeek }: MindmapProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const mmRef = useRef<Markmap | null>(null);
  const onSeekRef = useRef(onSeek);

  useEffect(() => {
    onSeekRef.current = onSeek;
  }, [onSeek]);

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

  // 事件委托：markmap 仅在折叠圆点上绑 click，节点文本无 click，
  // 故在 svg 上委托，命中带 data-t 的元素即跳转到对应时间
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
    <div className="border border-gray-200 rounded-lg p-2">
      {mindmap.ai_generated && <div className="text-xs text-accent-500 mb-1">AI 生成</div>}
      <svg ref={svgRef} className="w-full h-96" />
    </div>
  );
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
