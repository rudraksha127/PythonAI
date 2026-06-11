import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        forge: {
          base: "#0A0A0B",
          surface: "#111114",
          elevated: "#18181C",
          border: "#27272C",
          primary: "#5B5BFF",
          "primary-hover": "#4A4AFF",
          accent: "#06B6D4",
          glow: "rgba(91,91,255,0.15)",
        },
        text: {
          primary: "#FAFAFA",
          secondary: "#A1A1AA",
          muted: "#71717A",
        },
        success: "#22C55E",
        warning: "#F59E0B",
        error: "#EF4444",
      },
      fontFamily: {
        sans: ["Geist", "system-ui", "sans-serif"],
        mono: ["Geist Mono", "SF Mono", "Fira Code", "monospace"],
      },
      borderRadius: {
        DEFAULT: "8px",
      },
      animation: {
        "count-up": "countUp 0.6s ease-out",
        "pulse-glow": "pulseGlow 2s ease-in-out infinite",
      },
      keyframes: {
        countUp: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseGlow: {
          "0%, 100%": { boxShadow: "0 0 8px rgba(91,91,255,0.15)" },
          "50%": { boxShadow: "0 0 20px rgba(91,91,255,0.3)" },
        },
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
