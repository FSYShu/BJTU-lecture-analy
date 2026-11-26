import { useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { listCourses, courseKey, fetchReplays } from '@/api/courses';
import { useTaskStore } from '@/store/task';
import type { Course, Replay } from '@/types';

export default function CourseSidebar({ selectedReplayId: selectedReplayIdProp, expanded, onExpandedChange, replays: replaysProp }: { selectedReplayId?: number | null; expanded: boolean; onExpandedChange: (v: boolean) => void; replays?: Replay[] }) {
  const { courseKey: currentKey = '' } = useParams<{ courseKey: string }>();
  const [searchParams] = useSearchParams();
  const urlReplayId = searchParams.get('replay');
  const selectedReplayId = selectedReplayIdProp != null ? String(selectedReplayIdProp) : urlReplayId;
  const parseQueue = useTaskStore((s) => s.parseQueue);
  const [courses, setCourses] = useState<Course[]>([]);

  const [replayCounts, setReplayCounts] = useState<Record<number, number>>({});
  const [latestReplayDate, setLatestReplayDate] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(true);
  const justCollapsedRef = useRef(false);

  const handleCollapse = () => {
    onExpandedChange(false);
    justCollapsedRef.current = true;
    setTimeout(() => { justCollapsedRef.current = false; }, 400);
  };

  useEffect(() => {
    listCourses()
      .then((list) => {
        setCourses(list);
        if (list.length === 0) { setLoading(false); return; }
        let completed = 0;
        const total = list.length;
        list.forEach((c) => {
          fetchReplays(courseKey(c))
            .then((r) => {
              setReplayCounts((prev) => ({ ...prev, [c.id]: r.length }));
              const maxDate = r.reduce((max, replay) => {
                const raw = replay.teach_time_str || replay.class_begin_time || '';
                const digits = raw.replace(/\D/g, '');
                const num = digits.length >= 8 ? parseInt(digits) : 0;
                return Math.max(max, num);
              }, 0);
              setLatestReplayDate((prev) => ({ ...prev, [c.id]: maxDate }));
            })
            .catch(() => {})
            .finally(() => {
              completed++;
              if (completed === total) setLoading(false);
            });
        });
      })
      .catch(() => setLoading(false));
  }, []);

  const replays = replaysProp ?? [];

  return (
    <div className="shrink-0 h-full relative">
      <div
        className={`h-full flex flex-col transition-all duration-300 overflow-hidden ${
          expanded
            ? 'w-72 border-r border-gray-200 dark:border-gray-700/50 bg-gray-50/80 dark:bg-gray-800/50 backdrop-blur-sm'
            : 'w-0'
        }`}
      >
        <div className="min-w-[18rem] h-full flex flex-col">
          <div className="flex items-center px-4 py-3">
            <div className="flex items-center gap-2">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary-500 dark:text-primary-400">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200">课程列表</h3>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-3 sidebar-scroll">
            {loading ? (
              <div className="flex items-center justify-center gap-2 py-8">
                <div className="w-4 h-4 border-2 border-primary-300 border-t-primary-600 rounded-full animate-spin" />
                <span className="text-xs text-gray-400 dark:text-gray-500">加载中...</span>
              </div>
            ) : (
              <div className="space-y-1">
                {[...courses].sort((a, b) => (latestReplayDate[b.id] ?? 0) - (latestReplayDate[a.id] ?? 0)).map((c) => {
                  const key = courseKey(c);
                  const isCurrent = key === currentKey;
                  return (
                    <div key={c.id}>
                      <Link
                        to={`/courses/${key}`}
                        className={`relative block px-3 py-2.5 rounded-xl transition-all group ${
                          isCurrent
                            ? 'bg-primary-50 dark:bg-primary-900/30'
                            : 'hover:bg-white dark:hover:bg-gray-700/40'
                        }`}
                      >
                        {isCurrent && (
                          <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 rounded-r-full bg-primary-500 dark:bg-primary-400" />
                        )}
                        <div className={`text-sm leading-snug line-clamp-2 ${
                          isCurrent
                            ? 'text-primary-700 dark:text-primary-300 font-medium'
                            : 'text-gray-700 dark:text-gray-300 group-hover:text-gray-900 dark:group-hover:text-gray-100'
                        }`}>
                          {c.title}
                        </div>
                        <div className="flex items-center gap-1.5 mt-1">
                          {c.course_num && (
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                              isCurrent
                                ? 'bg-primary-100 dark:bg-primary-800/50 text-primary-600 dark:text-primary-400'
                                : 'bg-gray-100 dark:bg-gray-700/50 text-gray-400 dark:text-gray-500'
                            }`}>
                              {c.course_num}
                            </span>
                          )}
                          <span className="text-xs text-gray-400 dark:text-gray-500">
                            {c.teacher_name || ''}
                          </span>
                          {replayCounts[c.id] != null && replayCounts[c.id] > 0 && (
                            <span className={`text-[10px] ml-auto ${
                              isCurrent
                                ? 'text-primary-500 dark:text-primary-400'
                                : 'text-gray-400 dark:text-gray-500'
                            }`}>
                              {replayCounts[c.id]}节
                            </span>
                          )}
                        </div>
                      </Link>
                      {isCurrent && replays.length > 0 && (
                        <div className="ml-3 mt-0.5 mb-1 border-l border-gray-200 dark:border-gray-700 pl-2 space-y-0.5">
                          {replays.map((r) => {
                            const rawDate = r.teach_time_str || r.class_begin_time?.split(' ')[0] || '';
                            const digits = rawDate.replace(/\D/g, '');
                            const dateStr = digits.length >= 8
                              ? `${digits.slice(0,4)}-${digits.slice(4,6)}-${digits.slice(6,8)}`
                              : rawDate || '—';
                            const section = r.course_between?.replace(/^\d{4}[-/]?\d{2}[-/]?\d{2}\s*/, '') || '';
                            const isActive = selectedReplayId === String(r.id);
                            const isQueued = parseQueue.includes(r.id);
                            return (
                              <Link
                                key={r.id}
                                to={`/courses/${key}?replay=${r.id}`}
                                className={`block px-2 py-1.5 rounded transition-all ${
                                  isActive
                                    ? 'bg-primary-100 dark:bg-primary-900/40 font-medium'
                                    : isQueued
                                      ? 'bg-amber-50 dark:bg-amber-900/20'
                                      : 'hover:bg-gray-100 dark:hover:bg-gray-700/40'
                                }`}
                              >
                                <span className={`text-sm ${isActive ? 'text-primary-700 dark:text-primary-300' : 'text-gray-700 dark:text-gray-200'}`}>
                                  {dateStr}
                                </span>
                                {section && (
                                  <span className={`ml-1.5 text-xs ${isActive ? 'text-primary-500 dark:text-primary-400' : 'text-gray-400 dark:text-gray-500'}`}>
                                    {section}
                                  </span>
                                )}
                                {r.class_room && (
                                  <span className={`ml-1.5 text-xs ${isActive ? 'text-primary-400 dark:text-primary-500' : 'text-gray-400 dark:text-gray-500'}`}>
                                    {r.class_room}
                                  </span>
                                )}
                                {isQueued && (
                                  <span className="ml-1.5 text-[10px] text-amber-600 dark:text-amber-400 bg-amber-100 dark:bg-amber-800/40 px-1 rounded">
                                    排队中
                                  </span>
                                )}
                              </Link>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
      {expanded && (
        <button
          onClick={handleCollapse}
          className="absolute left-full top-1/2 -translate-y-1/2 w-6 h-12 flex items-center justify-center rounded-r-lg bg-primary-50 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400 hover:bg-primary-100 dark:hover:bg-primary-900/50 transition-all border border-l-0 border-gray-200 dark:border-gray-700"
          title="收起课程列表"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </button>
      )}
      {!expanded && (
        <>
          <div
            className="absolute left-full top-0 bottom-0 w-6 z-10"
            onMouseEnter={() => { if (!justCollapsedRef.current) onExpandedChange(true); }}
          />
          <button
            onClick={() => onExpandedChange(true)}
            className="absolute left-full top-1/2 -translate-y-1/2 w-6 h-12 flex items-center justify-center rounded-r-lg bg-primary-50 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400 hover:bg-primary-100 dark:hover:bg-primary-900/50 transition-all border border-l-0 border-gray-200 dark:border-gray-700"
            title="展开课程列表"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 18l6-6-6-6" />
            </svg>
          </button>
        </>
      )}
    </div>
  );
}