// 统一错误提示组件。
export default function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="bg-danger-50 dark:bg-danger-700/20 border border-danger-200 dark:border-danger-700 rounded-md p-3 text-sm text-danger-600 dark:text-danger-500">
      {message}
    </div>
  );
}
