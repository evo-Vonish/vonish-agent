/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: '#11110F',
        surface: { DEFAULT: '#1A1916', hover: '#222026', elevated: '#2A262E' },
        border: { DEFAULT: '#3D383F', hover: '#524D55' },
        foreground: { DEFAULT: '#E7E1D0', muted: '#A39B8F', subtle: '#6B6560' },
        primary: { DEFAULT: '#8FF6D2', hover: '#B9FFE8', muted: '#1A3D32' },
        success: '#56F28C', warning: '#D7B95A', error: '#B85A50', info: '#8FF6D2', thinking: '#8FF6D2',
        card: { DEFAULT: '#1A1916', foreground: '#E7E1D0' },
        popover: { DEFAULT: '#222026', foreground: '#E7E1D0' },
        secondary: { DEFAULT: '#222026', foreground: '#E7E1D0' },
        muted: { DEFAULT: '#222026', foreground: '#A39B8F' },
        accent: { DEFAULT: '#1A3D32', foreground: '#8FF6D2' },
        destructive: { DEFAULT: '#B85A50', foreground: '#E7E1D0' },
        ring: '#8FF6D2',
        input: '#3D383F',
      },
      borderRadius: { sm: '2px', DEFAULT: '4px', md: '6px', lg: '8px', xl: '8px', pill: '9999px' },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
