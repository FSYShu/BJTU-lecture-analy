import { useEffect, useState, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { client } from '@/api/client';
import { useAuthStore } from '@/store/auth';
import type { User } from '@/types';

interface CaptchaInitOut {
  captcha_image_base64: string;
  session_key: string;
}

interface CaptchaSubmitOut {
  user_id: number;

  access_token: string;
  user: User;
}

export default function CasLogin() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [captcha, setCaptcha] = useState('');
  const [captchaImage, setCaptchaImage] = useState('');
  const [sessionKey, setSessionKey] = useState('');
  const [loadingCaptcha, setLoadingCaptcha] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);

  const loadCaptcha = useCallback(async () => {
    setLoadingCaptcha(true);
    setError('');
    try {
      const { data } = await client.post<CaptchaInitOut>('/platform/captcha/init');
      setCaptchaImage(data.captcha_image_base64);
      setSessionKey(data.session_key);
      setCaptcha('');
    } catch (e: any) {
      const msg = e.response?.data?.message || e.response?.data?.detail;
      setError(msg || '加载验证码失败，请检查后端是否已启动');
    } finally {
      setLoadingCaptcha(false);
    }
  }, []);

  useEffect(() => {
    loadCaptcha();
  }, [loadCaptcha]);

  const submit = async () => {
    if (submitting) return;
    setSubmitting(true);
    setError('');
    try {
      const { data } = await client.post<CaptchaSubmitOut>('/platform/captcha/submit', {
        session_key: sessionKey,
        username,
        password,
        captcha_code: captcha,
      });
      setAuth(data.user, data.access_token);
      sessionStorage.removeItem('coursesSynced');
      navigate('/');
    } catch (e: any) {
      const msg = e.response?.data?.message || e.response?.data?.detail;
      setError(msg || '登录失败，验证码或账号密码可能错误');
      setPassword('');
      setCaptcha('');
      loadCaptcha();
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
          />
          <input
            className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
            type="password"
            placeholder="密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <div className="relative">
            <input
              className="w-full border border-gray-300 rounded-md px-3 py-2 pr-24 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
              placeholder="验证码"
              value={captcha}
              onChange={(e) => setCaptcha(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submit()}
            />
            {captchaImage && !loadingCaptcha ? (
              <img
                src={`data:image/png;base64,${captchaImage}`}
                alt="验证码"
                title="点击刷新"
                onClick={loadCaptcha}
                className="absolute right-1 top-1/2 -translate-y-1/2 h-8 rounded border border-gray-200 cursor-pointer hover:opacity-80 transition-opacity"
              />
            ) : (
              <div className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-20 rounded border border-gray-200 bg-gray-50 flex items-center justify-center text-xs text-gray-400">
                {loadingCaptcha ? '加载中...' : '无验证码'}
              </div>
            )}
          </div>
        </div>

        {error && <div className="text-sm text-danger-600">{error}</div>}
        <button
          className={`w-full bg-primary-600 text-white rounded-md py-2.5 font-medium hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${submitting ? 'animate-pulse' : ''}`}
          disabled={submitting || !username || !password || !captcha}
          onClick={submit}
        >
          {submitting ? '正在登录...' : '登录'}
        </button>
      </div>
    </div>
  );
}