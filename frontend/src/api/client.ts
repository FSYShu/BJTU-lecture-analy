import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export const client = axios.create({ baseURL: API_BASE_URL, timeout: 30000 });

/** 供 `fetch`（SSE 等非 axios 场景）复用的鉴权头。axios 拦截器只覆盖 axios 请求。 */
export function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (!token) {
    const url = config.url || '';
    if (url.includes('/captcha') || url.includes('/sso-login') || url.includes('/cas-login') || url.includes('/admin-login') || url.includes('/login')) {
      return config;
    }
    window.location.href = '/cas-login';
    return Promise.reject(new axios.Cancel('未登录'));
  }
  config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && !err.config.__retried) {
      err.config.__retried = true;
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/cas-login';
    }
    return Promise.reject(err);
  },
);
