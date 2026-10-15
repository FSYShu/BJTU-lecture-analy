import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { listCourses, startParse } from '@/api/courses';
import { ListSkeleton } from '@/components/Loading';
import Empty from '@/components/Empty';
import ErrorBanner from '@/components/ErrorBanner';
import { toast } from '@/store/toast';
import type { Course } from '@/types';

export default function CourseList() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [loadingId, setLoadingId] = useState<number | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    listCourses()
      .then((list) => setCourses(list))
      .catch(() => setError('课程列表加载失败，请稍后重试'))
      .finally(() => setLoading(false));
  }, []);

  const handleParse = async (c: Course) => {
    if (loadingId !== null) return;
    setLoadingId(c.id);
    try {
      await startParse(c.id);
      toast.success('已开始解析');
      navigate(`/courses/${c.id}`);
    } catch {
      toast.error('发起解析失败');
      setLoadingId(null);
    }
  };

  if (loading) return <ListSkeleton />;
  if (error) return <ErrorBanner message={error} />;
  if (!courses.length) return <Empty text="暂无课程回放" />;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">课程回放列表</h2>
      <div className="grid gap-3">
        {courses.map((c) => (
          <div
            key={c.id}
            className="border border-gray-200 rounded-lg p-4 flex items-center justify-between hover:shadow-md transition-shadow"
          >
            <Link to={`/courses/${c.id}`} className="flex-1 min-w-0">
              <div className="font-medium text-gray-800 truncate">{c.title}</div>
              <div className="text-sm text-gray-500">
                {[c.teacher_name, c.session_label].filter(Boolean).join(' · ') || '—'}
              </div>
            </Link>
            <button
              className="text-sm text-primary-600 hover:text-primary-700 hover:underline disabled:opacity-50 disabled:cursor-not-allowed shrink-0 ml-4"
              disabled={loadingId !== null}
              onClick={() => handleParse(c)}
            >
              {loadingId === c.id ? '解析中...' : '开始解析'}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
