import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { Course, Replay, Transcript, Keypoint, Summary, Mindmap } from '@/types';

export interface CourseDetailCache {
  course: Course | null;
  transcripts: Transcript[];
  keypoints: Keypoint[];
  summary: Summary | null;
  mindmap: Mindmap | null;
  replays: Replay[];
  selectedReplayId: number | null;
  replayVideoUrl: string;
  activeLectureId: number | null;
  activeTaskId: number | null;
  lastStep: string | null;
  fetchedAt: number;
}

interface CourseCacheState {
  cache: Record<string, CourseDetailCache>;
  patch: (courseKey: string, partial: Partial<CourseDetailCache>) => void;
  get: (courseKey: string) => CourseDetailCache | undefined;
  clear: (courseKey: string) => void;
}

const MAX_ENTRIES = 5;

const EMPTY: CourseDetailCache = {
  course: null,
  transcripts: [],
  keypoints: [],
  summary: null,
  mindmap: null,
  replays: [],
  selectedReplayId: null,
  replayVideoUrl: '',
  activeLectureId: null,
  activeTaskId: null,
  lastStep: null,
  fetchedAt: 0,
};

export const useCourseCacheStore = create<CourseCacheState>()(
  persist(
    (set, get) => ({
      cache: {},
      patch: (courseKey, partial) => {
        const cache = get().cache;
        const prev = cache[courseKey] ?? EMPTY;
        const next: CourseDetailCache = { ...prev, ...partial, fetchedAt: Date.now() };
        const entries = { ...cache, [courseKey]: next };
        const keys = Object.keys(entries);
        if (keys.length > MAX_ENTRIES) {
          keys.sort((a, b) => entries[a].fetchedAt - entries[b].fetchedAt);
          for (let i = 0; i < keys.length - MAX_ENTRIES; i++) {
            delete entries[keys[i]];
          }
        }
        set({ cache: entries });
      },
      get: (courseKey) => get().cache[courseKey],
      clear: (courseKey) => {
        const next = { ...get().cache };
        delete next[courseKey];
        set({ cache: next });
      },
    }),
    {
      name: 'course-detail-cache',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (s) => ({ cache: s.cache }),
    },
  ),
);

const secKey = (ck: string) => `cd-sec:${ck}`;

export function loadCurrentSec(courseKey: string): number {
  try {
    const raw = sessionStorage.getItem(secKey(courseKey));
    return raw ? Number(raw) || 0 : 0;
  } catch {
    return 0;
  }
}

export function saveCurrentSec(courseKey: string, sec: number): void {
  try {
    sessionStorage.setItem(secKey(courseKey), String(sec));
  } catch {
    /* noop */
  }
}