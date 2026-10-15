import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listCourses, startParse } from '@/api/courses';
import type { Course } from '@/types';

export default function CourseList() {
  const [courses, setCourses] = useState<Course[]>([]);
  useEffect(() => { listCourses().then(setCourses).catch(() => {}); }, []);

  return (
    <div>
      <h2 className="text-xl font-semibold mb-3">课程回放列表</h2>
      <div className="grid gap-3">
        {courses.map((c) => (
          <div key={c.id} className="border rounded p-3 flex items-center justify-between">
            <Link to={`/courses/${c.id}`} className="flex-1">
              <div className="font-medium">{c.title}</div>
              <div className="text-sm text-gray-500">{c.teacher_name} · {c.session_label}</div>
            </Link>
            <button className="text-sm text-blue-600 hover:underline" onClick={() => startParse(c.id)}>开始解析</button>
          </div>
        ))}
      </div>
    </div>
  );
}