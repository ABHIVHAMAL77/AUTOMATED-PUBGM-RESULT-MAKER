/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // The bronze/sand palette carried over from the original stylesheet, so
      // the rebuild still looks like the same product. Every value is a CSS
      // variable so light mode is a variable swap rather than a second theme.
      colors: {
        bg: "hsl(var(--bg) / <alpha-value>)",
        panel: "hsl(var(--panel) / <alpha-value>)",
        raised: "hsl(var(--raised) / <alpha-value>)",
        line: "hsl(var(--line) / <alpha-value>)",
        bronze: {
          DEFAULT: "hsl(var(--bronze) / <alpha-value>)",
          bright: "hsl(var(--bronze-bright) / <alpha-value>)",
        },
        sand: "hsl(var(--sand) / <alpha-value>)",
        muted: "hsl(var(--muted) / <alpha-value>)",
        ink: "hsl(var(--ink) / <alpha-value>)",
        danger: "hsl(var(--danger) / <alpha-value>)",
        warn: "hsl(var(--warn) / <alpha-value>)",
        ok: "hsl(var(--ok) / <alpha-value>)",
      },
      fontFamily: {
        sans: ['"Segoe UI"', "Inter", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "Consolas", "monospace"],
      },
      borderRadius: {
        panel: "14px",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "none" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
      animation: {
        "fade-in": "fade-in 160ms ease-out",
        shimmer: "shimmer 1.6s infinite",
      },
    },
  },
  plugins: [],
};
