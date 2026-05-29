/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: '#0d0d0d',
          secondary: '#111111',
        },
        surface: {
          DEFAULT: '#1a1a1a',
          hover: '#222222',
        },
        border: {
          DEFAULT: '#2a2a2a',
          light: '#333333',
        },
        accent: {
          DEFAULT: '#3b82f6',
          hover: '#2563eb',
        },
        text: {
          DEFAULT: '#e5e5e5',
          muted: '#888888',
          dim: '#555555',
        },
        code: {
          bg: '#141414',
          border: '#252525',
        }
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
