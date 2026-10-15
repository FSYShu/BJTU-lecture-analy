import { useToastStore } from '@/store/toast';

const STYLE: Record<string, string> = {
  success: 'bg-success-50 border-success-200 text-success-700',
  error: 'bg-danger-50 border-danger-200 text-danger-700',
  info: 'bg-primary-50 border-primary-200 text-primary-700',
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
