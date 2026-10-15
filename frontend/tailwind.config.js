/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff', 100: '#dbeafe', 200: '#bfdbfe', 300: '#93c5fd',
          400: '#60a5fa', 500: '#3b82f6', 600: '#2563eb',
          700: '#1d4ed8', 800: '#1e40af', 900: '#1e3a8a',
        },
        accent: {
          50: '#f5f3ff', 100: '#ede9fe', 200: '#ddd6fe',
          500: '#8b5cf6', 600: '#7c3aed', 700: '#6d28d9',
        },
        success: {
          50: '#f0fdf4', 100: '#dcfce7', 200: '#bbf7d0',
          500: '#22c55e', 600: '#16a34a', 700: '#15803d',
        },
        warning: {
          50: '#fffbeb', 100: '#fef3c7', 200: '#fde68a',
          500: '#f59e0b', 600: '#d97706', 700: '#b45309',
        },
        danger: {
          50: '#fef2f2', 100: '#fee2e2', 200: '#fecaca',
          500: '#ef4444', 600: '#dc2626', 700: '#b91c1c',
        },
      },
    },
  },
  plugins: [],
};
