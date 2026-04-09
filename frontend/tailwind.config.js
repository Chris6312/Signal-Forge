/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#6366f1',
          dark: '#4f46e5',
          glow: 'rgba(99, 102, 241, 0.15)',
        },
        surface: {
          DEFAULT: '#090a0f', // Deeper black for the void
          card: '#12141f',    // Slightly elevated
          border: '#1f2335',
          hover: '#1b1e2d',
        },
        system: {
          online: '#10b981',
          offline: '#ef4444',
          warning: '#f59e0b'
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        'brand-glow': '0 0 15px -3px rgba(99, 102, 241, 0.4)',
        'card-inset': 'inset 0 1px 0 0 rgba(255, 255, 255, 0.05)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }
    },
  },
  plugins: [],
}