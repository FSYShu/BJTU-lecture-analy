import { create } from 'zustand';
import type { User } from '@/types';

interface AuthState {
  user: User | null;
  token: string | null;
  setAuth: (user: User, token: string) => void;
  logout: () => void;
}

const storedUser = (() => {
  try {
    const raw = localStorage.getItem('user');
    return raw ? JSON.parse(raw) as User : null;
  } catch {
    return null;
  }
})();

export const useAuthStore = create<AuthState>((set) => ({
  user: storedUser,
  token: localStorage.getItem('token'),
  setAuth: (user, token) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
    set({ user, token });
  },
  logout: () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    set({ user: null, token: null });
  },
}));