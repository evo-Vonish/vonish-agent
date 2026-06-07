/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: '#0a0a0b',
        surface: { DEFAULT: '#141416', hover: '#1f1f21', elevated: '#252423' },
        border: { DEFAULT: 'rgba(255,255,255,0.08)', hover: 'rgba(255,255,255,0.14)' },
        foreground: { DEFAULT: '#e8e6e3', muted: '#9a9590', subtle: '#5c5855' },
        primary: { DEFAULT: '#c66a38', hover: '#a85830', muted: '#6f3a22' },
        success: '#22c55e', warning: '#f59e0b', error: '#ef4444', info: '#3b82f6', thinking: '#8b5cf6',
        card: { DEFAULT: '#1a1a1a', foreground: '#e0e0e0' },
        popover: { DEFAULT: '#1a1a1a', foreground: '#e0e0e0' },
        secondary: { DEFAULT: '#1a1a1a', foreground: '#e0e0e0' },
        muted: { DEFAULT: '#1a1a1a', foreground: '#888888' },
        accent: { DEFAULT: '#1a1a1a', foreground: '#e0e0e0' },
        destructive: { DEFAULT: '#ef4444', foreground: '#e0e0e0' },
        ring: '#c66a38',
        input: 'rgba(255,255,255,0.08)',
      },
      borderRadius: { sm: '4px', DEFAULT: '6px', md: '8px', lg: '12px', xl: '16px', pill: '9999px' },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
