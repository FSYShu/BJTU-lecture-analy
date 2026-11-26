import axios from 'axios';
import { useReLoginStore } from '@/store/relogin';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export const client = axios.create({ baseURL: API_BASE_URL, timeout: 30000 });

function authHeaders(): Record<string, string> {
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
    const store = useReLoginStore.getState();
    store.show();
    return new Promise((resolve, reject) => {
      store.enqueueRetry(async () => {
        try {
          const newToken = localStorage.getItem('token');
          if (newToken) {
            config.headers.Authorization = `Bearer ${newToken}`;
          }
          resolve(config);
        } catch (retryErr) {
          reject(retryErr);
        }
      });
    });
  }
  config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (r) => r,
  async (err) => {
    const code = err.response?.data?.code;

    if (code === 'COOKIES_EXPIRED' && !err.config.__reloginRetried) {
      err.config.__reloginRetried = true;
      const store = useReLoginStore.getState();
      store.show();
      return new Promise((resolve, reject) => {
        store.enqueueRetry(async () => {
          try {
            const newToken = localStorage.getItem('token');
            if (newToken) {
              err.config.headers.Authorization = `Bearer ${newToken}`;
            }
            const res = await client.request(err.config);
            resolve(res);
          } catch (retryErr) {
            reject(retryErr);
          }
        });
      });
    }

    if (err.response?.status === 401 && !err.config.__retried && code !== 'COOKIES_EXPIRED') {
      err.config.__retried = true;
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      const store = useReLoginStore.getState();
      store.show();
      return new Promise((resolve, reject) => {
        store.enqueueRetry(async () => {
          try {
            const newToken = localStorage.getItem('token');
            if (newToken) {
              err.config.headers.Authorization = `Bearer ${newToken}`;
            }
            const res = await client.request(err.config);
            resolve(res);
          } catch (retryErr) {
            reject(retryErr);
          }
        });
      });
    }
    return Promise.reject(err);
  },
);

export { authHeaders };
