import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listCourses, syncCourses, fetchReplays } from '@/api/courses';
import { GridSkeleton } from '@/components/Loading';
import Empty from '@/components/Empty';
import ErrorBanner from '@/components/ErrorBanner';
import { toast } from '@/store/toast';
import type { Course } from '@/types';

export default function CourseList() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [replayCounts, setReplayCounts] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    const doSync = !sessionStorage.getItem('coursesSynced');
    listCourses()
      .then((list) => {
        setCourses(list);
        list.forEach((c) => {
          fetchReplays(c.id)
            .then((replays) => setReplayCounts((prev) => ({ ...prev, [c.id]: replays.length })))
            .catch(() => {});
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
          list.forEach((c) => {
            fetchReplays(c.id)
              .then((replays) => setReplayCounts((prev) => ({ ...prev, [c.id]: replays.length })))
              .catch(() => {});
          });
        })
        .catch(() => toast.error('同步课程失败'))
        .finally(() => setSyncing(false));
    }
  }, []);

  if (loading || syncing) return <GridSkeleton />;
  if (error) return <ErrorBanner message={error} />;
  if (!courses.length) return <Empty text="暂无课程回放" />;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">课程列表</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {courses.map((c) => (
          <Link
            key={c.id}
            to={`/courses/${c.id}`}
            className="border border-gray-200 rounded-lg p-4 hover:shadow-md hover:border-primary-300 transition-all flex flex-col gap-2"
          >
            <div className="font-medium text-gray-800 line-clamp-2">{c.title}</div>
            <div className="text-sm text-gray-500">
              {c.course_num && c.fz_id ? `${c.course_num}[${c.fz_id.slice(-2)}]` : c.course_num || ''}
            </div>
            <div className="text-sm text-gray-400">
              {[c.teacher_name, c.session_label].filter(Boolean).join(' · ') || ''}
            </div>
            <div className="text-xs text-primary-600 mt-auto">
              {replayCounts[c.id] != null ? `${replayCounts[c.id]} 节回放` : ''}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
