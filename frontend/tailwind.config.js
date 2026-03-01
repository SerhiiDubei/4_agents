
/** @type {import('tailwindcss').Config} */
export default {
  content: [
  './index.html',
  './src/**/*.{js,ts,jsx,tsx}'
],
  theme: {
    extend: {
      colors: {
        game: {
          black: '#0a0a0f',
          darkPurple: '#1a0a2e',
          pink: '#ff2d6f',
          cyan: '#00f0ff',
          gold: '#ffd700',
          red: '#ff1744',
          gray: '#2a2a35',
          lightGray: '#8a8a9e',
        }
      },
      fontFamily: {
        pixel: ['"Press Start 2P"', 'cursive'],
        dialog: ['"VT323"', 'monospace'],
        impact: ['"Bebas Neue"', 'sans-serif'],
      },
      backgroundImage: {
        'scanlines': 'linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06))',
      }
    },
  },
  plugins: [],
}
