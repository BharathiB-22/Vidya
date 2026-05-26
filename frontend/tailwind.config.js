/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        sv: {
          dark:    '#0f2044',
          navy:    '#1a3564',
          primary: '#2563eb',
          accent:  '#06b6d4',
          muted:   '#94a3b8',
          light:   '#eef5ff',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
