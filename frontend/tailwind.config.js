/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Semantic typography tokens: `foreground` for primary content
        // (headings, titles, table/card data), `muted-foreground` for
        // secondary-only content (timestamps, helper text, placeholders,
        // metadata, disabled hints). See src/index.css for the CSS
        // variable definitions.
        foreground: 'rgb(var(--foreground) / <alpha-value>)',
        muted: {
          DEFAULT: 'rgb(var(--muted) / <alpha-value>)',
          foreground: 'rgb(var(--muted-foreground) / <alpha-value>)',
        },
        // University workspace (tenant side)
        sv: {
          dark:    '#0f2044',
          navy:    '#1a3564',
          primary: '#2563eb',
          accent:  '#06b6d4',
          muted:   '#94a3b8',
          light:   '#eef5ff',
        },
        // Platform Console (Super Admin side)
        plat: {
          bg:      '#060d1f',
          dark:    '#080f1e',
          surface: '#0c1629',
          card:    '#0e1831',
          border:  '#1a2a44',
          green:   '#10b981',
          'green-light': '#34d399',
          'green-dim':   '#064e3b',
          muted:   '#475569',
          text:    '#e2e8f0',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
