import { Outlet, Link } from 'react-router-dom';

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b px-4 py-2 flex items-center justify-between">
        <Link to="/" className="font-semibold">交大课录智析</Link>
        <nav className="space-x-4 text-sm">
          <Link to="/" className="hover:underline">课程列表</Link>
          <Link to="/admin/auth" className="hover:underline">授权管理</Link>
        </nav>
      </header>
      <main className="flex-1 p-4"><Outlet /></main>
    </div>
  );
}