import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef7ff",
          100: "#d9ecff",
          200: "#bcdeff",
          300: "#8ecaff",
          400: "#59abff",
          500: "#3b8bff",
          600: "#1b65f5",
          700: "#1550e1",
          800: "#1841b6",
          900: "#1a3a8f",
          950: "#142557",
        },
        dark: {
          50: "#f6f6f9",
          100: "#ececf2",
          200: "#d5d5e2",
          300: "#b1b1c8",
          400: "#8686a9",
          500: "#66668f",
          600: "#525276",
          700: "#434360",
          800: "#3a3a51",
          900: "#121220",
          950: "#0a0a14",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
