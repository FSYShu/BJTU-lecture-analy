import type { Summary } from '@/types';

export default function SummaryView({ summary }: { summary: Summary }) {
  let chapters: any[] = [];
  let details: any[] = [];
  let hints: any[] = [];
  try { chapters = JSON.parse(summary.chapter_points || '[]'); } catch {}
  try { details = JSON.parse(summary.key_details || '[]'); } catch {}
  try { hints = JSON.parse(summary.review_hints || '[]'); } catch {}

  return (
    <div className="border rounded p-4 space-y-4">
      {summary.ai_generated && <div className="text-xs text-gray-400">AI 生成</div>}
      {summary.overview && (
        <section>
          <h3 className="font-semibold mb-1">课程概览</h3>
          <p className="text-sm text-gray-700">{summary.overview}</p>
        </section>
      )}
      {chapters.length > 0 && (
        <section>
          <h3 className="font-semibold mb-1">章节要点</h3>
          <ul className="text-sm list-disc pl-5">
            {chapters.map((c, i) => <li key={i}>{c.chapter}</li>)}
          </ul>
        </section>
      )}
      {details.length > 0 && (
        <section>
          <h3 className="font-semibold mb-1">重点详解</h3>
          <ul className="text-sm list-disc pl-5">
            {details.map((d, i) => <li key={i}>{d}</li>)}
          </ul>
        </section>
      )}
      {hints.length > 0 && (
        <section>
          <h3 className="font-semibold mb-1">复习提示</h3>
          <ul className="text-sm list-disc pl-5">
            {hints.map((h, i) => <li key={i}>{h}</li>)}
          </ul>
        </section>
      )}
    </div>
  );
}