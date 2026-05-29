/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: '#0d0d0d',
        surface: { DEFAULT: '#1a1a1a', hover: '#222222', elevated: '#252525' },
        border: { DEFAULT: '#2a2a2a', hover: '#3a3a3a' },
        foreground: { DEFAULT: '#e0e0e0', muted: '#888888', subtle: '#555555' },
        primary: { DEFAULT: '#4f46e5', hover: '#4338ca', muted: '#3730a3' },
        success: '#22c55e', warning: '#f59e0b', error: '#ef4444', info: '#3b82f6', thinking: '#8b5cf6',
        card: { DEFAULT: '#1a1a1a', foreground: '#e0e0e0' },
        popover: { DEFAULT: '#1a1a1a', foreground: '#e0e0e0' },
        secondary: { DEFAULT: '#1a1a1a', foreground: '#e0e0e0' },
        muted: { DEFAULT: '#1a1a1a', foreground: '#888888' },
        accent: { DEFAULT: '#1a1a1a', foreground: '#e0e0e0' },
        destructive: { DEFAULT: '#ef4444', foreground: '#e0e0e0' },
        ring: '#4f46e5',
        input: '#2a2a2a',
      },
      borderRadius: { sm: '4px', DEFAULT: '6px', md: '8px', lg: '12px', xl: '16px', pill: '9999px' },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
