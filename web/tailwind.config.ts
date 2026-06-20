import type { Config } from 'tailwindcss'

// 深色金融配色 design token
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0a0e17',
        bg2: '#0e1320',
        card: 'rgba(255,255,255,0.035)',
        'card-strong': 'rgba(255,255,255,0.06)',
        line: 'rgba(255,255,255,0.09)',
        accent: '#22d3ee',
        'accent-2': '#a78bfa',
        up: '#34d399',
        down: '#f87171',
        warn: '#fbbf24',
        text: '#e6edf3',
        dim: '#8b97a7',
      },
      borderRadius: { DEFAULT: '12px', sm: '8px', lg: '16px' },
      fontFamily: {
        sans: ['-apple-system', 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Menlo', 'monospace'],
      },
      boxShadow: {
        accent: '0 2px 10px rgba(34,211,238,.22)',
        'accent-hover': '0 4px 16px rgba(34,211,238,.4)',
      },
    },
  },
  plugins: [],
} satisfies Config
