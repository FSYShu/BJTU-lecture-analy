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

  // 用 ref 持有最新 onSeek，避免因 seek 函数变化重建 markmap
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

    const mm = mmRef.current;
    // 覆盖点击处理：从节点内容解析 @timestamp 触发跳转，同时保留节点折叠行为
    const original = mm.handleClick.bind(mm);
    mm.handleClick = (e, node) => {
      const m = /@(\d+(?:\.\d+)?)/.exec(node?.content || '');
      if (m) onSeekRef.current?.(parseFloat(m[1]));
      original(e, node);
    };

    return () => {
      mmRef.current?.destroy();
      mmRef.current = null;
    };
  }, [md]);

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
      md += `- ${kp.name}${kp.timestamp_sec != null ? ` @${kp.timestamp_sec}` : ''}\n`;
    }
  }
  return md;
}
