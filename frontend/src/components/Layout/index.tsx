import { Outlet, Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';
import TaskBadge from '@/components/TaskBadge';
import { useTheme } from '@/hooks/useTheme';

export default function Layout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const { theme, toggle } = useTheme();
  const isDark = theme === 'dark';

  const handleLogout = () => {
    logout();
    navigate('/cas-login');
  };

  return (
    <div className="min-h-screen flex flex-col bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 transition-colors">
      <header className="h-14 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 sticky top-0 z-50 flex items-center justify-between px-6">
        <div className="flex items-center gap-6">
          <Link to="/" className="text-lg font-bold text-gray-800 dark:text-gray-100">交大课录智析</Link>
          <Link to="/" className="text-sm text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">课程列表</Link>
        </div>
        <nav className="flex items-center gap-6 text-sm">
          {user?.role === 'admin' && (
            <Link to="/admin/auth" className="text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">授权管理</Link>
          )}
          <button
            onClick={toggle}
            title={isDark ? '切换到浅色模式' : '切换到深色模式'}
            aria-label={isDark ? '切换到浅色模式' : '切换到深色模式'}
            className="text-gray-500 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
          >
            {isDark ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
              </svg>
            )}
          </button>
          <TaskBadge />
          {user ? (
            <>
              <span className="text-gray-500 dark:text-gray-400">{user.username}</span>
              <button onClick={handleLogout} className="text-gray-400 dark:text-gray-500 hover:text-danger-600 dark:hover:text-danger-500 transition-colors">退出</button>
            </>
          ) : (
            <Link to="/cas-login" className="text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">登录</Link>
          )}
        </nav>
      </header>
      <main className="flex-1 p-6">
        <Outlet />
      </main>
      <footer className="h-10 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 flex items-center justify-center text-xs text-gray-400 dark:text-gray-500">
        AI 生成内容仅供参考 · v0.1.0
      </footer>
    </div>
  );
}