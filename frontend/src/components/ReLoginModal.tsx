import { useState } from 'react';
import { client } from '@/api/client';
import { useAuthStore } from '@/store/auth';
import { useReLoginStore } from '@/store/relogin';
import { toast } from '@/store/toast';
import type { User } from '@/types';

interface SsoLoginOut {
  user_id: number;
  access_token: string;
  user: User;
}

export default function ReLoginModal() {
  const visible = useReLoginStore((s) => s.visible);
  const hide = useReLoginStore((s) => s.hide);
  const drainRetries = useReLoginStore((s) => s.drainRetries);
  const setAuth = useAuthStore((s) => s.setAuth);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (!visible) return null;

  const submit = async () => {
    if (submitting || !username || !password) return;
    setSubmitting(true);
    setError('');
    try {
      const { data } = await client.post<SsoLoginOut>('/platform/sso-login', {
        username,
        password,
      });
      setAuth(data.user, data.access_token);
      toast.success('重新登录成功');
      drainRetries();
      setPassword('');
      setUsername('');
    } catch (e: any) {
      const msg = e.response?.data?.message || e.response?.data?.detail;
      setError(msg || '登录失败，请检查账号密码');
      setPassword('');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = () => {
    hide();
    setPassword('');
    setUsername('');
    setError('');
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl p-6 max-w-sm w-full mx-4 space-y-4">
        <h3 className="text-lg font-bold text-center">平台登录已过期</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 text-center -mt-2">
          请重新输入账号密码以继续使用
        </p>

        <div className="space-y-2">
          <input
            className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 rounded-md px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
            placeholder="学号 / 教工号"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            autoFocus
          />
          <input
            className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 rounded-md px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
            type="password"
            placeholder="密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
          />
        </div>

        {error && <div className="text-sm text-danger-600 dark:text-danger-500">{error}</div>}

        <div className="flex gap-3">
          <button
            className="flex-1 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-md py-2.5 font-medium hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            onClick={handleCancel}
            disabled={submitting}
          >
            取消
          </button>
          <button
            className={`flex-1 bg-primary-600 text-white rounded-md py-2.5 font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${submitting ? 'animate-pulse' : ''}`}
            disabled={submitting || !username || !password}
            onClick={submit}
          >
            {submitting ? '正在登录...' : '重新登录'}
          </button>
        </div>
      </div>
    </div>
  );
}