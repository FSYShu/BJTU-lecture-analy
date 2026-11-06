import { create } from 'zustand';
import type { Task } from '@/types';

interface TaskState {
  task: Task | null;
  setTask: (task: Task | null) => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  task: null,
  setTask: (task) => set({ task }),
}));