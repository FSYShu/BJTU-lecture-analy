import { useToastStore } from '@/store/toast';

const STYLE: Record<string, string> = {
  success: 'bg-success-50 dark:bg-success-700/20 border-success-200 dark:border-success-700 text-success-700 dark:text-success-500',
  error: 'bg-danger-50 dark:bg-danger-700/20 border-danger-200 dark:border-danger-700 text-danger-700 dark:text-danger-500',
  info: 'bg-primary-50 dark:bg-primary-900/40 border-primary-200 dark:border-primary-700 text-primary-700 dark:text-primary-300',
};

export default function Toast() {
  const toasts = useToastStore((s) => s.toasts);
  return (
    <div className="fixed top-4 right-4 z-[100] space-y-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`px-4 py-2 rounded-md border text-sm shadow-lg ${STYLE[t.type] ?? STYLE.info}`}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}
