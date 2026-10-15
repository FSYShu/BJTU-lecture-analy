import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { client } from '@/api/client';
import { useAuthStore } from '@/store/auth';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);

  const submit = async () => {
    const { data } = await client.post('/auth/login', { username, password });
    setAuth(data.user, data.access_token);
    navigate('/');
  };

  return (
    <div className="max-w-sm mx-auto mt-20 space-y-3">
      <h2 className="text-xl font-semibold">登录</h2>
      <input className="w-full border rounded px-3 py-2" placeholder="用户名" value={username} onChange={(e) => setUsername(e.target.value)} />
      <input className="w-full border rounded px-3 py-2" type="password" placeholder="密码" value={password} onChange={(e) => setPassword(e.target.value)} />
      <button className="w-full bg-blue-600 text-white rounded py-2" onClick={submit}>登录</button>
    </div>
  );
}