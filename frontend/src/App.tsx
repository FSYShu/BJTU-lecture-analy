import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Login from './pages/Login';
import CasLogin from './pages/CasLogin';
import CourseList from './pages/CourseList';
import CourseDetail from './pages/CourseDetail';
import AdminAuth from './pages/AdminAuth';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/admin-login" element={<Login />} />
      <Route path="/cas-login" element={<CasLogin />} />
      <Route element={<Layout />}>
        <Route path="/" element={<CourseList />} />
        <Route path="/courses/:id" element={<CourseDetail />} />
        <Route path="/admin/auth" element={<AdminAuth />} />
      </Route>
    </Routes>
  );
}
