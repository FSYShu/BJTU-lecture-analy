// 统一空状态组件。
export default function Empty({ text }: { text: string }) {
  return <div className="text-gray-400 text-sm text-center py-8">{text}</div>;
}
