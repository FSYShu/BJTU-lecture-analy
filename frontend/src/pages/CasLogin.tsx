import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { client } from '@/api/client';
import { useAuthStore } from '@/store/auth';
import type { User } from '@/types';

interface SsoLoginOut {
  user_id: number;
  access_token: string;
  user: User;
}

export default function CasLogin() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);

  const submit = async () => {
    if (submitting) return;
    setSubmitting(true);
    setError('');
    try {
      const { data } = await client.post<SsoLoginOut>('/platform/sso-login', {
        username,
        password,
      });
      setAuth(data.user, data.access_token);
      sessionStorage.removeItem('coursesSynced');
      navigate('/');
    } catch (e: any) {
      const msg = e.response?.data?.message || e.response?.data?.detail;
      setError(msg || '登录失败，请检查账号密码');
      setPassword('');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-start justify-center relative">
      <Link
        to="/admin-login"
        className="absolute top-4 right-6 text-xs text-gray-400 hover:text-gray-600 transition-colors"
      >
        管理员登录
      </Link>
      <div className="bg-white shadow-lg rounded-xl p-8 max-w-sm w-full mt-32 space-y-4">
        <h2 className="text-2xl font-bold text-center">交大课录智析</h2>
        <p className="text-sm text-gray-500 text-center -mt-2">北交大统一身份认证</p>

        <div className="space-y-2">
          <input
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
            placeholder="学号 / 教工号"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
          />
          <input
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
            type="password"
            placeholder="密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
          />
        </div>

        {error && <div className="text-sm text-danger-600">{error}</div>}
        <button
          className={`w-full bg-primary-600 text-white rounded-md py-2.5 font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${submitting ? 'animate-pulse' : ''}`}
          disabled={submitting || !username || !password}
          onClick={submit}
        >
          {submitting ? '正在登录...' : '立即登录'}
        </button>
      </div>
    </div>
  );
}