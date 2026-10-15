import { Outlet, Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';

export default function Layout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <header className="h-14 border-b border-gray-200 bg-white sticky top-0 z-50 flex items-center justify-between px-6">
        <Link to="/" className="text-lg font-bold text-gray-800">交大课录智析</Link>
        <nav className="flex items-center gap-6 text-sm">
          <Link to="/" className="text-gray-600 hover:text-primary-600 transition-colors">课程列表</Link>
          {user?.role === 'admin' && (
            <Link to="/admin/auth" className="text-gray-600 hover:text-primary-600 transition-colors">授权管理</Link>
          )}
          {user ? (
            <button onClick={handleLogout} className="text-gray-400 hover:text-danger-600 transition-colors">退出</button>
          ) : (
            <Link to="/login" className="text-gray-600 hover:text-primary-600 transition-colors">登录</Link>
          )}
        </nav>
      </header>
      <main className="flex-1 p-6">
        <Outlet />
      </main>
      <footer className="h-10 border-t border-gray-200 bg-white flex items-center justify-center text-xs text-gray-400">
        AI 生成内容仅供参考 · v0.1.0
      </footer>
    </div>
  );
}
