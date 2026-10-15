import { useEffect, useRef } from 'react';
import { Transformer } from 'markmap-lib';
import { Markmap } from 'markmap-view';
import 'markmap-view/style.css';
import type { Mindmap } from '@/types';

interface MindmapProps {
  mindmap: Mindmap;
  onSeek?: (t: number) => void;
}

export default function MindmapView({ mindmap, onSeek }: MindmapProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  // 两级结构 → markdown
  const md = buildMarkdown(mindmap);

  useEffect(() => {
    if (!svgRef.current) return;
    const { root } = new Transformer().transform(md);
    Markmap.create(svgRef.current, undefined, root);
  }, [md]);

  return (
    <div className="border rounded p-2">
      {mindmap.ai_generated && <div className="text-xs text-gray-400 mb-1">AI 生成</div>}
      <svg ref={svgRef} className="w-full h-96" />
    </div>
  );
}

function buildMarkdown(m: Mindmap): string {
  let nodes: any[] = [];
  try { nodes = JSON.parse(m.nodes); } catch {}
  let md = `# ${m.root_topic}\n`;
  for (const mod of nodes) {
    md += `## ${mod.module}\n`;
    for (const kp of mod.knowledge_points || []) {
      md += `- ${kp.name}${kp.timestamp_sec != null ? ` @${kp.timestamp_sec}` : ''}\n`;
    }
  }
  return md;
}