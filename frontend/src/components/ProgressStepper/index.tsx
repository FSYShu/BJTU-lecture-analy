interface ProgressStepperProps {
  status: string;
  progress: number;
  currentStep?: string;
  elapsedSec: number;
  lastUpdateSec: number;
}

const STEPS = [
  { key: 'downloading', label: '元数据' },
  { key: 'extracting_audio', label: '提取音频' },
  { key: 'asr_running', label: '语音识别' },
  { key: 'llm_running', label: 'AI 解析' },
  { key: 'persisting', label: '保存结果' },
];

const STEP_ORDER = ['queued', 'downloading', 'extracting_audio', 'asr_running', 'llm_running', 'persisting', 'succeeded'];

function formatSize(kb: number): string {
  if (kb < 1024) return `${kb}KB`;
  return `${(kb / 1024).toFixed(1)}MB`;
}

function formatTime(raw: string): string {
  const match = raw.match(/(\d+):(\d+):(\d+)/);
  if (!match) return raw;
  const [, h, m, s] = match;
  if (h === '00') return `${m}:${s}`;
  return `${h}:${m}:${s}`;
}

function parseStepDetail(currentStep?: string): { label: string; sub?: string } | null {
  if (!currentStep) return null;
  const parts = currentStep.split('|');
  const type = parts[0];

  if (type === 'audio' && parts.length >= 4) {
    const time = formatTime(parts[1]);
    const speed = parts[2];
    const size = formatSize(parseInt(parts[3]) || 0);
    return { label: '提取音频', sub: `已处理 ${time} · 速度 ${speed} · ${size}` };
  }

  if (type === 'asr' && parts.length >= 3) {
    const current = parts[1];
    const msg = parts[2] || '';
    return { label: '语音识别', sub: `分片 ${current}${msg ? ' · ' + msg : ''}` };
  }

  return null;
}

export default function ProgressStepper({ status, progress, currentStep, elapsedSec, lastUpdateSec }: ProgressStepperProps) {
  const currentIdx = STEP_ORDER.indexOf(status);
  const isSucceeded = status === 'succeeded';
  const isFailed = status === 'failed';

  const detail = parseStepDetail(currentStep);
  const elapsed = `${Math.floor(elapsedSec / 60)}:${String(elapsedSec % 60).padStart(2, '0')}`;

  return (
    <div className="border border-gray-200 rounded-lg p-4 bg-gray-50 space-y-3">
      {/* Stepper */}
      <div className="flex items-center gap-1">
        {STEPS.map((step, idx) => {
          const stepStatusIdx = STEP_ORDER.indexOf(step.key);
          let state: 'done' | 'active' | 'pending' | 'failed' = 'pending';

          if (isSucceeded) {
            state = 'done';
          } else if (isFailed) {
            state = stepStatusIdx < currentIdx ? 'done' : stepStatusIdx === currentIdx ? 'failed' : 'pending';
          } else {
            state = stepStatusIdx < currentIdx ? 'done' : stepStatusIdx === currentIdx ? 'active' : 'pending';
          }

          return (
            <div key={step.key} className="flex items-center gap-1 flex-1">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="shrink-0">
                  {state === 'done' && <span className="inline-flex w-5 h-5 rounded-full bg-green-500 text-white text-xs items-center justify-center">✓</span>}
                  {state === 'active' && <span className="inline-flex w-5 h-5 rounded-full bg-primary-500 text-white text-xs items-center justify-center animate-pulse">●</span>}
                  {state === 'failed' && <span className="inline-flex w-5 h-5 rounded-full bg-red-500 text-white text-xs items-center justify-center">✕</span>}
                  {state === 'pending' && <span className="inline-flex w-5 h-5 rounded-full border-2 border-gray-300 text-transparent text-xs items-center justify-center">○</span>}
                </span>
                <span className={`text-xs truncate ${state === 'active' ? 'font-semibold text-primary-700' : state === 'done' ? 'text-gray-500' : state === 'failed' ? 'text-red-600 font-medium' : 'text-gray-400'}`}>
                  {step.label}
                </span>
              </div>
              {idx < STEPS.length - 1 && (
                <div className={`h-0.5 flex-1 rounded ${state === 'done' ? 'bg-green-400' : 'bg-gray-200'}`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
        <div
          className={`h-2.5 rounded-full transition-all duration-500 relative ${isFailed ? 'bg-red-500' : 'bg-primary-500'}`}
          style={{ width: `${progress}%` }}
        >
          {!isFailed && !isSucceeded && (
            <span className="absolute right-0 top-0 h-2.5 w-12 bg-gradient-to-r from-transparent to-white/50 animate-pulse" />
          )}
        </div>
      </div>

      {/* Detail line */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-3">
          {isSucceeded ? (
            <span className="text-green-600 font-medium">✓ 解析完成</span>
          ) : isFailed ? (
            <span className="text-red-600 font-medium">解析失败</span>
          ) : (
            <span className="text-gray-600 font-medium">
              {detail?.label || STEPS[Math.max(0, currentIdx - 1)]?.label || '处理中'}
            </span>
          )}
          {detail?.sub && !isSucceeded && !isFailed && (
            <span className="text-gray-400">{detail.sub}</span>
          )}
        </div>
        <div className="flex items-center gap-3 text-gray-400">
          <span>{progress}%</span>
          <span>已用 {elapsed}</span>
          {lastUpdateSec >= 0 && <span>更新 {lastUpdateSec}s 前</span>}
        </div>
      </div>
    </div>
  );
}