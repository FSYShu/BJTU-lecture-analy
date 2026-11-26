import { create } from 'zustand';

interface ReLoginState {
  visible: boolean;
  pendingRequests: Array<() => void>;
  show: () => void;
  hide: () => void;
  enqueueRetry: (fn: () => void) => void;
  drainRetries: () => void;
}

export const useReLoginStore = create<ReLoginState>((set, get) => ({
  visible: false,
  pendingRequests: [],
  show: () => set({ visible: true }),
  hide: () => set({ visible: false }),
  enqueueRetry: (fn) => set((s) => ({ pendingRequests: [...s.pendingRequests, fn] })),
  drainRetries: () => {
    const fns = get().pendingRequests;
    set({ pendingRequests: [], visible: false });
    fns.forEach((fn) => fn());
  },
}));