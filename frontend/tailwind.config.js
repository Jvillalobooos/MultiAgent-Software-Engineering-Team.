export default {
  content: [
  './index.html',
  './src/**/*.{js,ts,jsx,tsx}'
],
  theme: {
    extend: {
      colors: {
        void: '#04060c',
        hull: {
          900: '#05080f',
          800: '#080d18',
          700: '#0b1120',
          600: '#101a2d',
          500: '#18243c',
          400: '#243352',
        },
        electric: '#3fb6ff',
        amber: '#ffb545',
        neon: '#49e08a',
        plasma: '#a98bff',
        alert: '#ff5c6e',
        mist: '#8fa3c4',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      boxShadow: {
        'glow-electric': '0 0 0 1px rgba(63,182,255,0.45), 0 0 24px -4px rgba(63,182,255,0.55)',
        'glow-amber': '0 0 0 1px rgba(255,181,69,0.45), 0 0 24px -4px rgba(255,181,69,0.5)',
        'glow-neon': '0 0 0 1px rgba(73,224,138,0.45), 0 0 24px -4px rgba(73,224,138,0.5)',
        'glow-alert': '0 0 0 1px rgba(255,92,110,0.5), 0 0 26px -4px rgba(255,92,110,0.55)',
        panel: '0 18px 50px -24px rgba(0,0,0,0.9), inset 0 1px 0 rgba(255,255,255,0.05)',
      },
      transitionTimingFunction: {
        command: 'cubic-bezier(0.23, 1, 0.32, 1)',
      },
    },
  },
  plugins: [],
}
