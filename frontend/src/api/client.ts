import axios from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export const client = axios.create({ baseURL, timeout: 30000 });

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