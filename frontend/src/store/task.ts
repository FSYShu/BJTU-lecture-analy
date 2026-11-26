import { create } from 'zustand';
import type { Task } from '@/types';

interface TaskState {
  task: Task | null;
  activeTasks: Task[];
  parseQueue: number[];
  setTask: (task: Task | null) => void;
  setActiveTasks: (tasks: Task[]) => void;
  addParseQueue: (id: number) => void;
  removeParseQueue: (id: number) => void;
  clearParseQueue: () => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  task: null,
  activeTasks: [],
  parseQueue: [],
  setTask: (task) => set({ task }),
  setActiveTasks: (tasks) => set({ activeTasks: tasks }),
  addParseQueue: (id) => set((s) => s.parseQueue.includes(id) ? s : { parseQueue: [...s.parseQueue, id] }),
  removeParseQueue: (id) => set((s) => ({ parseQueue: s.parseQueue.filter((q) => q !== id) })),
  clearParseQueue: () => set({ parseQueue: [] }),
}));