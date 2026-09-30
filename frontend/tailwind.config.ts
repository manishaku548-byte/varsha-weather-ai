import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          50: "#eef4fb",
          100: "#d9e6f5",
          200: "#b3cce8",
          300: "#7fa8d4",
          400: "#4a7fb8",
          500: "#2a5f9e",
          600: "#1c4a83",
          700: "#153a6b",
          800: "#0f2e52",
          900: "#0a2342",
        },
        teal: {
          50: "#f0fdfa",
          100: "#ccfbf1",
          200: "#99f6e4",
          300: "#5eead4",
          400: "#2dd4bf",
          500: "#14b8a6",
          600: "#0d9488",
          700: "#0f766e",
          800: "#115e59",
          900: "#134e4a",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        panel: "0 1px 2px rgba(15, 46, 82, 0.06), 0 2px 8px rgba(15, 46, 82, 0.05)",
      },
    },
  },
  plugins: [],
};

export default config;