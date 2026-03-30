import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './hooks/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        background: '#0d1117',
        panel: '#1a1a2e',
        'panel-light': '#16213e',
        border: '#2a2a4a',
        'border-light': '#3a3a5a',
        accent: '#ecad0a',
        primary: '#209dd7',
        secondary: '#753991',
        'price-up': '#22c55e',
        'price-down': '#ef4444',
        'text-primary': '#e6e6e6',
        'text-secondary': '#8b8b9e',
        'text-muted': '#5a5a7a',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', 'monospace'],
      },
      animation: {
        'flash-up': 'flashUp 500ms ease-out',
        'flash-down': 'flashDown 500ms ease-out',
        'fade-in': 'fadeIn 200ms ease-in',
      },
      keyframes: {
        flashUp: {
          '0%': { backgroundColor: '#166534' },
          '100%': { backgroundColor: 'transparent' },
        },
        flashDown: {
          '0%': { backgroundColor: '#7f1d1d' },
          '100%': { backgroundColor: 'transparent' },
        },
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
export default config
