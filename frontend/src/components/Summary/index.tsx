import type { Summary } from '@/types';

export default function SummaryView({ summary }: { summary: Summary }) {
  let chapters: any[] = [];
  let details: any[] = [];
  let hints: any[] = [];
  try { chapters = JSON.parse(summary.chapter_points || '[]'); } catch { /* 容错 */ }
  try { details = JSON.parse(summary.key_details || '[]'); } catch { /* 容错 */ }
  try { hints = JSON.parse(summary.review_hints || '[]'); } catch { /* 容错 */ }

  return (
    <div className="border border-gray-200 rounded-lg p-4 space-y-4">
      {summary.ai_generated && <div className="text-xs text-accent-500 text-right -mb-2">AI 生成</div>}
      {summary.overview && (
        <section>
          <h3 className="font-semibold text-base mb-1">课程概览</h3>
          <p className="text-sm text-gray-700 leading-relaxed">{summary.overview}</p>
        </section>
      )}
      {chapters.length > 0 && (
        <section>
          <h3 className="font-semibold text-base mb-1">章节要点</h3>
          <div className="space-y-2">
            {chapters.map((c, i) => (
              <div key={i}>
                <div className="text-sm font-semibold text-gray-900">{c.chapter ?? c}</div>
                {Array.isArray(c.points) && c.points.length > 0 && (
                  <ul className="text-sm list-disc pl-5 mt-0.5 space-y-0.5 text-gray-600">
                    {c.points.map((p: string, j: number) => <li key={j}>{p}</li>)}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
      {details.length > 0 && (
        <section>
          <h3 className="font-semibold text-base mb-2">重点详解</h3>
          <div className="space-y-3">
            {details.map((d, i) => (
              <div key={i} className="border-l-2 border-gray-200 pl-3">
                {typeof d === 'string' ? (
                  <p className="text-sm text-gray-700 leading-relaxed">{d}</p>
                ) : (
                  <>
                    {d.title && <div className="text-sm font-semibold text-gray-900">{d.title}</div>}
                    {d.detail && <p className="text-sm text-gray-600 leading-relaxed mt-0.5">{d.detail}</p>}
                  </>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
      {hints.length > 0 && (
        <section>
          <h3 className="font-semibold text-base mb-1">复习提示</h3>
          <ul className="text-sm list-disc pl-5 space-y-1 text-gray-700">
            {hints.map((h, i) => <li key={i}>{typeof h === 'string' ? h : h.text ?? JSON.stringify(h)}</li>)}
          </ul>
        </section>
      )}
    </div>
  );
}
