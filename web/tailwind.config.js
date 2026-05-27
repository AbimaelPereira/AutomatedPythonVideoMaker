/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      colors: {
        navy: {
          50:  '#e8edf5',
          100: '#c5d0e6',
          200: '#9fb0d4',
          300: '#7890c2',
          400: '#5a76b5',
          500: '#3d5ca8',
          600: '#2f4a8f',
          700: '#1e3470',
          800: '#132354',
          900: '#0a1530',
          950: '#060d1e',
        },
      },
    },
  },
  plugins: [],
}
