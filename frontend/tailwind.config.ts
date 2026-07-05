import type { Config } from "tailwindcss";

// Design tokens — see docs/05-design-system.md
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0B0E11",
        surface: "#12161C",
        "surface-2": "#181D25",
        border: "#232A33",
        text: "#E6EAF0",
        "text-dim": "#8B93A1",
        "text-faint": "#5A6270",
        up: "#2EBD85",
        down: "#F6465D",
        accent: "#4A9EFF",
        warn: "#F0B90B",
        crit: "#FF5C5C",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 0 0 1px #232A33, 0 8px 24px rgb(0 0 0 / 0.35)",
        glow: "0 0 0 1px #4A9EFF33, 0 0 20px #4A9EFF22",
      },
      borderRadius: { lg: "8px" },
    },
  },
  plugins: [],
};
export default config;
