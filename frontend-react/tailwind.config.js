/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#111827',
        panel: '#ffffff',
        muted: '#64748b',
        safety: {
          red: '#dc2626',
          amber: '#d97706',
          green: '#16a34a',
          blue: '#2563eb',
          teal: '#0f766e',
        },
      },
      boxShadow: {
        soft: '0 18px 45px rgba(15, 23, 42, 0.08)',
        insetLine: 'inset 0 0 0 1px rgba(15, 23, 42, 0.08)',
      },
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [],
};
