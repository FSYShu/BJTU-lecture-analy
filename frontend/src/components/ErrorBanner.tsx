// 统一错误提示组件。
export default function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="bg-danger-50 border border-danger-200 rounded-md p-3 text-sm text-danger-600">
      {message}
    </div>
  );
}
