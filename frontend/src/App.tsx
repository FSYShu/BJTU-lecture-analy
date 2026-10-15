import { Routes, Route } from 'react-router-dom';
import Login from './pages/Login';
import CourseList from './pages/CourseList';
import CourseDetail from './pages/CourseDetail';
import AdminAuth from './pages/AdminAuth';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<CourseList />} />
      <Route path="/login" element={<Login />} />
      <Route path="/courses/:id" element={<CourseDetail />} />
      <Route path="/admin/auth" element={<AdminAuth />} />
    </Routes>
  );
}