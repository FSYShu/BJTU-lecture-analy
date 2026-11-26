import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { listCourses, syncCourses, fetchReplays, courseKey } from '@/api/courses';
import { listActiveTasks } from '@/api/tasks';
import { GridSkeleton } from '@/components/Loading';
import ErrorBanner from '@/components/ErrorBanner';
import { useAuthStore } from '@/store/auth';
import { toast } from '@/store/toast';
import type { Course, Replay, Task } from '@/types';

type SortKey = 'replays' | 'title' | 'updated';
type FilterKey = 'all' | 'hasReplays';

interface ReplayWithCourse extends Replay {
  course: Course;
  key: string;
}

function formatTeachTimeShort(raw?: string | null): string {
  if (!raw) return '';
  const digits = raw.replace(/\D/g, '');
  if (digits.length >= 8) return `${digits.slice(4, 6)}-${digits.slice(6, 8)}`;
  return raw;
}

function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function greetingByHour(): string {
  const h = new Date().getHours();
  if (h < 6) return '夜深了';
  if (h < 12) return '早上好';
  if (h < 14) return '中午好';
  if (h < 18) return '下午好';
  return '晚上好';
}

function teacherInitial(name?: string): string {
  if (!name) return '?';
  return name.charAt(0);
}




const STATUS_LABEL: Record<string, string> = {
  queued: '排队中',
  downloading: '获取元数据',
  extracting_audio: '提取音频',
  asr_running: '语音识别',
  llm_running: 'AI 解析',
  persisting: '保存结果',
  succeeded: '解析完成',
  failed: '解析失败',
};

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

const PERIOD_ROWS = [
  { label: '1-2节', startHour: 8 },
  { label: '3-4节', startHour: 10 },
  { label: '5-6节', startHour: 14 },
  { label: '7-8节', startHour: 16 },
  { label: '9-10节', startHour: 19 },
  { label: '11节', startHour: 21 },
];

function parseWeekday(teachTimeStr?: string | null): number | null {
  if (!teachTimeStr) return null;
  const digits = teachTimeStr.replace(/\D/g, '');
  if (digits.length < 8) return null;
  const y = parseInt(digits.slice(0, 4));
  const m = parseInt(digits.slice(4, 6)) - 1;
  const d = parseInt(digits.slice(6, 8));
  const date = new Date(y, m, d);
  return date.getDay();
}

function parsePeriod(classBeginTime?: string | null, courseBetween?: string | null): number | null {
  let hour: number | null = null;
  if (classBeginTime) {
    const m = classBeginTime.match(/(\d{2}):(\d{2})/);
    if (m) hour = parseInt(m[1]);
  }
  if (hour === null && courseBetween) {
    const m = courseBetween.match(/(\d{2}):(\d{2})-\d{2}:\d{2}/);
    if (m) hour = parseInt(m[1]);
  }
  if (hour === null) return null;
  for (let i = 0; i < PERIOD_ROWS.length; i++) {
    if (hour >= PERIOD_ROWS[i].startHour && hour < (PERIOD_ROWS[i + 1]?.startHour ?? 24)) {
      return i;
    }
  }
  return null;
}


interface ScheduleCell {
  replay: ReplayWithCourse;
  weekday: number;
  period: number;
}

export default function CourseList() {
  const user = useAuthStore((s) => s.user);
  const [courses, setCourses] = useState<Course[]>([]);
  const [allReplays, setAllReplays] = useState<ReplayWithCourse[]>([]);
  const [replayCounts, setReplayCounts] = useState<Record<number, number>>({});
  const [parsedCounts, setParsedCounts] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(true);
  const [replaysLoaded, setReplaysLoaded] = useState(false);
  const [error, setError] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('replays');
  const [filterKey, setFilterKey] = useState<FilterKey>('all');
  const [activeTasks, setActiveTasks] = useState<Task[]>([]);

  useEffect(() => {
    const doSync = !sessionStorage.getItem('coursesSynced');
    listCourses()
      .then((list) => {
        setCourses(list);
        Promise.all(
          list.map((c) =>
            fetchReplays(courseKey(c))
              .then((replays) => {
                setReplayCounts((prev) => ({ ...prev, [c.id]: replays.length }));
                setParsedCounts((prev) => ({
                  ...prev,
                  [c.id]: replays.filter((r) => r.has_result).length,
                }));
                return replays.map((r) => ({ ...r, course: c, key: courseKey(c) }));
              })
              .catch(() => []),
          ),
        ).then((results) => {
          setAllReplays(results.flat());
          setReplaysLoaded(true);
        });
      })
      .catch(() => setError('课程列表加载失败，请稍后重试'))
      .finally(() => setLoading(false));

    if (doSync) {
      setSyncing(true);
      syncCourses()
        .then(() => {
          sessionStorage.setItem('coursesSynced', '1');
          return listCourses();
        })
        .then((list) => {
          setCourses(list);
          Promise.all(
            list.map((c) =>
              fetchReplays(courseKey(c))
                .then((replays) => {
                  setReplayCounts((prev) => ({ ...prev, [c.id]: replays.length }));
                  setParsedCounts((prev) => ({
                    ...prev,
                    [c.id]: replays.filter((r) => r.has_result).length,
                  }));
                  return replays.map((r) => ({ ...r, course: c, key: courseKey(c) }));
                })
                .catch(() => []),
            ),
          ).then((results) => {
            setAllReplays(results.flat());
            setReplaysLoaded(true);
          });
        })
        .catch(() => toast.error('同步课程失败'))
        .finally(() => setSyncing(false));
    }

    listActiveTasks()
      .then(setActiveTasks)
      .catch(() => {});
  }, []);

  const totalReplays = useMemo(
    () => Object.values(replayCounts).reduce((sum, n) => sum + n, 0),
    [replayCounts],
  );

  const totalParsed = useMemo(
    () => Object.values(parsedCounts).reduce((sum, n) => sum + n, 0),
    [parsedCounts],
  );

  const scheduleCells = useMemo<ScheduleCell[]>(() => {
    const cells: ScheduleCell[] = [];
    for (const r of allReplays) {
      const weekday = parseWeekday(r.teach_time_str);
      const period = parsePeriod(r.class_begin_time, r.course_between);
      if (weekday !== null && period !== null) {
        cells.push({ replay: r, weekday, period });
      }
    }
    const seen = new Map<string, ScheduleCell>();
    for (const cell of cells) {
      const key = `${cell.weekday}-${cell.period}`;
      const existing = seen.get(key);
      if (!existing || (cell.replay.teach_time_str ?? '') > (existing.replay.teach_time_str ?? '')) {
        seen.set(key, cell);
      }
    }
    return Array.from(seen.values()).sort((a, b) => a.period - b.period || a.weekday - b.weekday);
  }, [allReplays]);

  const recentReplays = useMemo(() => {
    return [...allReplays]
      .sort((a, b) => {
        const ta = a.teach_time_str ?? a.class_begin_time ?? '';
        const tb = b.teach_time_str ?? b.class_begin_time ?? '';
        return tb.localeCompare(ta);
      })
      .slice(0, 5);
  }, [allReplays]);

  const filteredCourses = useMemo(() => {
    const kw = search.trim().toLowerCase();
    let list = courses;
    if (kw) {
      list = list.filter(
        (c) =>
          c.title.toLowerCase().includes(kw) ||
          (c.course_num ?? '').toLowerCase().includes(kw) ||
          (c.teacher_name ?? '').toLowerCase().includes(kw),
      );
    }
    if (filterKey === 'hasReplays') {
      list = list.filter((c) => (replayCounts[c.id] ?? 0) > 0);
    }
    const sorted = [...list];
    if (sortKey === 'replays') {
      sorted.sort((a, b) => (replayCounts[b.id] ?? 0) - (replayCounts[a.id] ?? 0));
    } else if (sortKey === 'title') {
      sorted.sort((a, b) => a.title.localeCompare(b.title, 'zh'));
    } else {
      sorted.sort((a, b) => b.id - a.id);
    }
    return sorted;
  }, [courses, search, sortKey, filterKey, replayCounts]);

  if (loading || syncing) return <GridSkeleton />;
  if (error) return <ErrorBanner message={error} />;

  const greeting = user?.display_name || user?.username || '同学';
  const latestReplay = recentReplays[0];
  const subtitle = latestReplay
    ? `上次更新：${latestReplay.course.title} · ${formatTeachTimeShort(latestReplay.teach_time_str)}`
    : '开始探索你的课程回放吧';

  const todayWeekday = new Date().getDay();
  const activePeriodRows = PERIOD_ROWS
    .map((row, i) => ({ label: row.label, startHour: row.startHour, originalIdx: i }));
  const displayWeekdays = [1, 2, 3, 4, 5, 6, 0];

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      {/* 欢迎横幅 */}
      <div className="relative rounded-2xl overflow-hidden bg-gradient-to-br from-primary-500 via-primary-600 to-primary-700 p-8">
        <div className="absolute inset-0 backdrop-blur-xl bg-white/10 dark:bg-black/10" />
        <svg className="absolute inset-0 w-full h-full opacity-[0.07]" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
              <path d="M 24 0 L 0 0 0 24" fill="none" stroke="white" strokeWidth="0.5" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>
        <div className="absolute -right-8 -top-8 w-40 h-40 rounded-full bg-white/10 blur-2xl" />
        <div className="absolute -left-4 -bottom-4 w-32 h-32 rounded-full bg-white/5 blur-xl" />
        <div className="relative flex items-center justify-between">
          <div className="min-w-0">
            <h2 className="text-3xl font-bold text-white">{greetingByHour()}，{greeting}</h2>
            <p className="text-base text-white/70 mt-1">{todayStr()}</p>
            <p className="text-base text-white/80 mt-2 truncate">{subtitle}</p>
            <div className="flex items-center gap-4 mt-4 text-white/90">
              <span className="flex items-center gap-2 text-base">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
                  <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
                </svg>
                {courses.length} 门课程
              </span>
              <span className="text-white/30">|</span>
              <span className="flex items-center gap-2 text-base">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="4" width="20" height="16" rx="2" />
                  <path d="M10 9l5 3-5 3z" />
                </svg>
                {totalReplays} 节回放
              </span>
              {totalParsed > 0 && (
                <>
                  <span className="text-white/30">|</span>
                  <span className="flex items-center gap-2 text-base">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    {totalParsed} 节已解析
                  </span>
                </>
              )}
            </div>
          </div>
          {latestReplay && (
            <Link
              to={`/courses/${latestReplay.key}`}
              className="shrink-0 flex items-center gap-2 px-5 py-3 rounded-xl bg-white/20 hover:bg-white/30 backdrop-blur-sm text-white text-base font-medium transition-all hover:scale-105"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
               <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              继续学习
            </Link>
          )}
        </div>
      </div>

      {/* 课程表 */}
      {!replaysLoaded ? (
        <div>
          <h3 className="text-lg font-semibold mb-3">课程表</h3>
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
            <div className="grid" style={{ gridTemplateColumns: `80px repeat(${displayWeekdays.length}, 1fr)` }}>
              {/* 表头 */}
              <div className="p-2 text-base text-gray-400 dark:text-gray-500 border-b border-gray-200 dark:border-gray-700" />
              {displayWeekdays.map((wd) => (
                <div key={wd} className="p-2 text-center text-base font-medium border-b border-gray-200 dark:border-gray-700 text-gray-400 dark:text-gray-500">
                  {WEEKDAYS[wd]}
                </div>
              ))}
              {PERIOD_ROWS.map((row, i) => (
                <div key={row.label} className="contents">
                  {i > 0 && (i === 2 || i === 4) && (
                    <div className="contents">
                      <div className="h-5 border-b border-gray-200 dark:border-gray-600" />
                      {displayWeekdays.map((wd) => (
                        <div key={wd} className="h-5 border-b border-gray-200 dark:border-gray-600" />
                      ))}
                    </div>
                  )}
                  <div className="p-2 text-base text-gray-300 dark:text-gray-600 border-b border-gray-100 dark:border-gray-700/50 flex items-center font-medium">
                    {row.label}
                  </div>
                  {displayWeekdays.map((wd) => (
                    <div key={wd} className="border-b border-gray-100 dark:border-gray-700/50 border-l border-gray-100 dark:border-gray-700/50 h-[72px] animate-pulse bg-gray-50 dark:bg-gray-700/30" />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : scheduleCells.length > 0 ? (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-semibold">课程表</h3>
            <span className="text-xs text-gray-400 dark:text-gray-500">{scheduleCells.length} 个课位</span>
          </div>
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
            <div className="grid" style={{ gridTemplateColumns: `80px repeat(${displayWeekdays.length}, 1fr)` }}>
              {/* 表头 */}
              <div className="p-2 text-base text-gray-400 dark:text-gray-500 border-b border-gray-200 dark:border-gray-700" />
              {displayWeekdays.map((wd) => (
                <div
                  key={wd}
                  className={`p-2 text-center text-base font-medium border-b border-gray-200 dark:border-gray-700 ${
                    wd === todayWeekday
                      ? 'text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20'
                      : 'text-gray-500 dark:text-gray-400'
                  }`}
                >
                  {WEEKDAYS[wd]}
                </div>
              ))}
              {/* 表体 */}
              {activePeriodRows.map((row, mapIdx) => (
                <div key={row.label} className="contents">
                  {/* 4-5节之间、8-9节之间加矮空行 */}
                  {mapIdx > 0 && (row.originalIdx === 2 || row.originalIdx === 4) && (
                    <div className="contents">
                      <div className="h-5 border-b border-gray-200 dark:border-gray-600" />
                      {displayWeekdays.map((wd) => (
                        <div key={wd} className="h-5 border-b border-gray-200 dark:border-gray-600" />
                      ))}
                    </div>
                  )}
                  <div className="p-2 text-base text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-700/50 flex items-center font-medium">
                    {row.label}
                  </div>
                  {displayWeekdays.map((wd) => {
                    const cell = scheduleCells.find((c) => c.weekday === wd && c.period === row.originalIdx);
                    if (!cell) {
                      return (
                        <div
                          key={wd}
                          className="border-b border-gray-100 dark:border-gray-700/50 border-l border-gray-100 dark:border-gray-700/50 h-[80px]"
                        />
                      );
                    }
                    const r = cell.replay;
                    return (
                      <Link
                        key={wd}
                        to={`/courses/${r.key}`}
                        className="group relative border-b border-gray-100 dark:border-gray-700/50 border-l border-gray-100 dark:border-gray-700/50 p-2 h-[80px] flex flex-col gap-1 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors overflow-hidden"
                      >
                        <div className="text-base font-medium text-gray-800 dark:text-gray-100 line-clamp-2">
                          {r.course.title}
                        </div>
                        <div className="text-sm text-gray-400 dark:text-gray-500">
                          {r.class_room || ''}
                        </div>

                        {r.has_result && (
                          <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-success-500" title="已解析" />
                        )}
                      </Link>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      {/* 解析任务 */}
      {activeTasks.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary-500">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            </svg>
            <h3 className="text-lg font-semibold">解析任务</h3>
            <span className="text-sm text-gray-400 dark:text-gray-500">{activeTasks.length} 个进行中</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {activeTasks.slice(0, 4).map((t) => (
              <div
                key={t.id}
                className={`flex items-center gap-3 rounded-xl border p-4 transition-shadow hover:shadow-md ${
                  t.status === 'failed'
                    ? 'border-red-200 dark:border-red-800/50 bg-red-50/50 dark:bg-red-900/10'
                    : t.status === 'succeeded'
                      ? 'border-success-200 dark:border-success-800/50 bg-success-50/50 dark:bg-success-900/10'
                      : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800'
                }`}
              >
                <div className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center ${
                  t.status === 'failed'
                    ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
                    : t.status === 'succeeded'
                      ? 'bg-success-100 dark:bg-success-900/30 text-success-600 dark:text-success-500'
                      : 'bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400'
                }`}>
                  {t.status === 'failed' ? (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10" />
                      <line x1="15" y1="9" x2="9" y2="15" />
                      <line x1="9" y1="9" x2="15" y2="15" />
                    </svg>
                  ) : t.status === 'succeeded' ? (
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  ) : (
                    <svg className="animate-spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                    </svg>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-base font-medium text-gray-800 dark:text-gray-100 truncate">
                    {t.course_title || `课程 #${t.course_id}`}
                  </div>
                  <div className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                    {STATUS_LABEL[t.status] || t.status}
                    {t.status !== 'queued' && ` · ${t.progress}%`}
                  </div>
                </div>
                <div className="w-24 bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden shrink-0">
                  <div
                    className={`h-2 rounded-full transition-all duration-500 ${
                      t.status === 'failed' ? 'bg-red-500' : t.status === 'succeeded' ? 'bg-success-500' : 'bg-primary-500'
                    }`}
                    style={{ width: `${t.status === 'queued' ? 0 : t.progress}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 我的课程 */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-primary-500">
                <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
                <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
              </svg>
              <h3 className="text-lg font-semibold">我的课程</h3>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setFilterKey('all')}
                className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                  filterKey === 'all'
                    ? 'bg-primary-100 dark:bg-primary-900/40 text-primary-600 dark:text-primary-400 font-medium'
                    : 'text-gray-400 dark:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`}
              >
                全部
              </button>
              <button
                onClick={() => setFilterKey('hasReplays')}
                className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                  filterKey === 'hasReplays'
                    ? 'bg-primary-100 dark:bg-primary-900/40 text-primary-600 dark:text-primary-400 font-medium'
                    : 'text-gray-400 dark:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`}
              >
                有回放
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <svg
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500"
                width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
              >
                <circle cx="11" cy="11" r="8" />
                <path d="M21 21l-4.3-4.3" />
              </svg>
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索课程"
                className="w-44 pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:border-primary-400 dark:focus:border-primary-500 focus:ring-2 focus:ring-primary-100 dark:focus:ring-primary-900/30 transition-all"
              />
            </div>
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
              className="px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 focus:outline-none focus:border-primary-400 dark:focus:border-primary-500 transition-colors cursor-pointer"
            >
              <option value="replays">按回放数</option>
              <option value="title">按课程名</option>
              <option value="updated">按最近更新</option>
            </select>
          </div>
        </div>

        {filteredCourses.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <svg
              className="text-gray-300 dark:text-gray-600 mb-3"
              width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
            >
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
              <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
            </svg>
            <p className="text-gray-400 dark:text-gray-500 text-sm">
              {search ? '没有匹配的课程' : '暂无课程回放'}
            </p>
            {search && (
              <button
                onClick={() => setSearch('')}
                className="mt-2 text-sm text-primary-600 dark:text-primary-400 hover:underline"
              >
                清除搜索
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filteredCourses.map((c) => {
              const count = replayCounts[c.id];
              const parsed = parsedCounts[c.id] ?? 0;
              const parseRatio = count > 0 ? (parsed / count) * 100 : 0;
              return (
                <Link
                  key={c.id}
                  to={`/courses/${courseKey(c)}`}
                  className="group relative border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden bg-white dark:bg-gray-800 hover:shadow-xl hover:border-primary-300 dark:hover:border-primary-500 hover:-translate-y-1 transition-all flex flex-col"
                >
                  <div className="h-1 bg-gradient-to-r from-primary-400 to-primary-600 opacity-0 group-hover:opacity-100 transition-opacity" />
                  <div className="p-4 flex flex-col gap-3 flex-1">
                    <div className="flex items-start gap-3">
                      <div
                        className="shrink-0 w-10 h-10 rounded-full flex items-center justify-center text-base font-semibold text-white bg-primary-500"
                      >
                        {teacherInitial(c.teacher_name)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-base text-gray-800 dark:text-gray-100 line-clamp-2">{c.title}</div>
                        <div className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                          {c.course_num && c.fz_id ? `${c.course_num}[${c.fz_id.slice(-2)}]` : c.course_num || ''}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center justify-between mt-auto">
                      <div className="text-sm text-gray-400 dark:text-gray-500">
                        {[c.teacher_name, c.session_label].filter(Boolean).join(' · ') || ''}
                      </div>
                      {count != null && count > 0 && (
                        <span className="px-2.5 py-0.5 text-sm rounded-full bg-primary-50 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400">
                          {count} 节
                        </span>
                      )}
                    </div>
                    {count > 0 && (
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                          <div
                            className="h-1.5 rounded-full bg-gradient-to-r from-primary-400 to-primary-600 transition-all duration-500"
                            style={{ width: `${parseRatio}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">
                          {parsed}/{count}
                        </span>
                      </div>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
