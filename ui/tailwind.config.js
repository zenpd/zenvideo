/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        zen: {
          50:  '#f0f4ff',
          100: '#e0eaff',
          200: '#c7d7fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
          950: '#1e1b4b',
        },
      },
      boxShadow: {
        'card':         '0 1px 3px 0 rgba(0,0,0,.06), 0 1px 2px -1px rgba(0,0,0,.06)',
        'card-hover':   '0 8px 24px -4px rgba(79,70,229,.18), 0 2px 8px -2px rgba(0,0,0,.08)',
        'header':       '0 1px 0 #e5e7eb',
        'glow-zen':     '0 0 16px 2px rgba(99,102,241,.35)',
        'glow-emerald': '0 0 12px 2px rgba(16,185,129,.30)',
        'glow-amber':   '0 0 12px 2px rgba(245,158,11,.30)',
      },
      backgroundImage: {
        'gradient-zen':      'linear-gradient(135deg, #6366f1 0%, #4f46e5 50%, #4338ca 100%)',
        'gradient-zen-soft': 'linear-gradient(135deg, #f0f4ff 0%, #e0eaff 100%)',
        'gradient-amber':    'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
        'gradient-violet':   'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)',
        'gradient-emerald':  'linear-gradient(135deg, #10b981 0%, #059669 100%)',
        'shimmer':           'linear-gradient(90deg, transparent 0%, rgba(255,255,255,.6) 50%, transparent 100%)',
      },
      animation: {
        'fade-in':   'fadeIn 0.2s ease-out',
        'slide-up':  'slideUp 0.25s ease-out',
        'pulse-dot': 'pulseDot 1.5s ease-in-out infinite',
        'pulse-ring':'pulseRing 2s ease-out infinite',
        'shimmer':   'shimmer 2s ease-in-out infinite',
        'spin-slow': 'spin 3s linear infinite',
      },
      keyframes: {
        fadeIn:    { from: { opacity: 0 },                                        to: { opacity: 1 } },
        slideUp:   { from: { opacity: 0, transform: 'translateY(8px)' },          to: { opacity: 1, transform: 'translateY(0)' } },
        pulseDot:  { '0%,100%': { opacity: 1 },                                   '50%': { opacity: 0.4 } },
        pulseRing: { '0%': { transform: 'scale(.9)', opacity: .7 },               '70%': { transform: 'scale(1.4)', opacity: 0 }, '100%': { transform: 'scale(.9)', opacity: 0 } },
        shimmer:   { '0%': { backgroundPosition: '-400px 0' },                    '100%': { backgroundPosition: '400px 0' } },
      },
    },
  },
  plugins: [],
  safelist: [
    // Stage accent colors — all variants used dynamically
    { pattern: /^(bg|text|border|ring)-(amber|violet|zen|emerald)-(50|100|200|400|500|600|700)$/ },
    { pattern: /^bg-(amber|violet|zen|emerald)-50\/(30|50)$/ },
    { pattern: /^from-(amber|violet|zen|emerald)-(400|500|600)$/ },
    { pattern: /^to-(amber|violet|zen|emerald)-(400|500|600)$/ },
    { pattern: /^shadow-glow-(zen|emerald|amber)$/ },
  ],
}
