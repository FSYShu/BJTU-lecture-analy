import { useEffect, useState } from 'react';
import { client } from '@/api/client';
import { toast } from '@/store/toast';

interface Authorization {
  id: number;
  course_id: number;
  user_id: number;
  course_title?: string;
  student_name?: string;
  is_revoked: boolean;
  created_at: string;
}

export default function AdminAuth() {
  const [courseId, setCourseId] = useState('');
  const [userId, setUserId] = useState('');
  const [auths, setAuths] = useState<Authorization[]>([]);
  const [granting, setGranting] = useState(false);

  const load = () => {
    client.get<Authorization[]>('/admin/authorizations')
      .then((r) => setAuths(r.data))
      .catch(() => {});
  };

  useEffect(() => { load(); }, []);

  const grant = async () => {
    if (granting) return;
    setGranting(true);
    try {
      await client.post('/admin/authorizations', { course_id: Number(courseId), user_id: Number(userId) });
      toast.success('授权成功');
      setCourseId('');
      setUserId('');
      load();
    } catch {
      toast.error('授权失败，请检查输入');
    } finally {
      setGranting(false);
    }
  };

  const revoke = async (id: number) => {
    try {
      await client.post(`/admin/authorizations/${id}/revoke`);
      toast.success('已撤销授权');
      load();
    } catch {
      toast.error('撤销失败');
    }
  };

  return (
    <div className="max-w-3xl space-y-6">
      <h2 className="text-2xl font-bold">课程授权管理</h2>

      <div className="flex gap-3 items-end">
        <div className="flex-1 space-y-1">
          <label className="text-sm text-gray-600">课程 ID</label>
          <input
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
            placeholder="课程 ID"
            value={courseId}
            onChange={(e) => setCourseId(e.target.value)}
          />
        </div>
        <div className="flex-1 space-y-1">
          <label className="text-sm text-gray-600">学生 ID</label>
          <input
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
            placeholder="学生 ID"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
          />
        </div>
        <button
          className="bg-primary-600 text-white rounded-md px-4 py-2 hover:bg-primary-700 transition-colors disabled:opacity-50"
          disabled={granting}
          onClick={grant}
        >
          {granting ? '授权中...' : '授权'}
        </button>
      </div>

      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="bg-gray-50 text-gray-600 text-left">
              <th className="px-4 py-2 font-medium">课程</th>
              <th className="px-4 py-2 font-medium">学生</th>
              <th className="px-4 py-2 font-medium">状态</th>
              <th className="px-4 py-2 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {auths.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-400">暂无授权记录</td>
              </tr>
            ) : (
              auths.map((a) => (
                <tr key={a.id} className="border-t border-gray-100">
                  <td className="px-4 py-2">{a.course_title ?? a.course_id}</td>
                  <td className="px-4 py-2">{a.student_name ?? a.user_id}</td>
                  <td className="px-4 py-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${a.is_revoked ? 'bg-gray-100 text-gray-500' : 'bg-success-100 text-success-700'}`}>
                      {a.is_revoked ? '已撤销' : '有效'}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    {!a.is_revoked && (
                      <button className="text-sm text-danger-600 hover:underline" onClick={() => revoke(a.id)}>撤销</button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
