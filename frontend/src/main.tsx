import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import Toast from './components/Toast';
import { initTheme } from './hooks/useTheme';
import './styles/index.css';

initTheme();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
      <Toast />
    </BrowserRouter>
  </React.StrictMode>,
);
