import { useState } from 'react';
import { client } from '@/api/client';

export default function AdminAuth() {
  const [courseId, setCourseId] = useState('');
  const [userId, setUserId] = useState('');

  const grant = async () => {
    await client.post('/admin/authorizations', { course_id: Number(courseId), user_id: Number(userId) });
    alert('授权成功');
  };

  return (
    <div className="max-w-md space-y-3">
      <h2 className="text-xl font-semibold">课程授权管理</h2>
      <input className="w-full border rounded px-3 py-2" placeholder="课程 ID" value={courseId} onChange={(e) => setCourseId(e.target.value)} />
      <input className="w-full border rounded px-3 py-2" placeholder="学生 ID" value={userId} onChange={(e) => setUserId(e.target.value)} />
      <button className="bg-blue-600 text-white rounded px-4 py-2" onClick={grant}>授权</button>
    </div>
  );
}