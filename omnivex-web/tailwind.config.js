/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['var(--font-display)'],
        mono: ['var(--font-mono)', 'monospace'],
      },
      colors: {
        obsidian: {
          950: '#080a0f',
          900: '#0d1017',
          800: '#131720',
          700: '#1a2030',
          600: '#222840',
        },
        gold: {
          400: '#d4a843',
          300: '#e8c56a',
          200: '#f0d898',
        },
        alpha:  { DEFAULT: '#22d3a0', dim: '#22d3a020' },
        hedge:  { DEFAULT: '#f04f4f', dim: '#f04f4f20' },
        core:   { DEFAULT: '#f0a640', dim: '#f0a64020' },
      },
    },
  },
  plugins: [],
}
