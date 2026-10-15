import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { client } from '@/api/client';
import { useAuthStore } from '@/store/auth';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);

  const submit = async () => {
    if (loading) return;
    setLoading(true);
    setError('');
    try {
      const { data } = await client.post('/auth/login', { username, password });
      setAuth(data.user, data.access_token);
      navigate('/');
    } catch {
      setError('登录失败，请检查用户名和密码');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-start justify-center">
      <div className="bg-white shadow-lg rounded-xl p-8 max-w-sm w-full mt-32 space-y-4">
        <h2 className="text-2xl font-bold text-center">交大课录智析</h2>
        <div className="space-y-2">
          <input
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
            placeholder="用户名"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <input
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
            type="password"
            placeholder="密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && <div className="text-sm text-danger-600">{error}</div>}
        <button
          className={`w-full bg-primary-600 text-white rounded-md py-2.5 font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${loading ? 'animate-pulse' : ''}`}
          disabled={loading}
          onClick={submit}
        >
          {loading ? '登录中...' : '登录'}
        </button>
      </div>
    </div>
  );
}
