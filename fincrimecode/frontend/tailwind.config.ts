import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: "#0070AD", 50: "#E6F2F9", 100: "#CCE4F2", 600: "#0070AD", 700: "#005F93" },
        secondary: { DEFAULT: "#004C7F", 900: "#00375C" },
        success: "#28A745",
        warning: "#FFC107",
        danger: "#DC3545",
      },
      fontFamily: { sans: ["Inter", "Segoe UI", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
export default config;
