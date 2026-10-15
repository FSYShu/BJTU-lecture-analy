// 统一骨架屏组件。用于列表/区块加载态。
export function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse bg-gray-200 rounded ${className ?? ''}`} />;
}

// 列表页骨架屏（3 个灰色块）。
export function ListSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="border border-gray-200 rounded-lg p-4">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-3 w-1/3 mt-2" />
        </div>
      ))}
    </div>
  );
}
