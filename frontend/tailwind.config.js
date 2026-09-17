/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#d9e6ff",
          200: "#b3ccff",
          300: "#80a8ff",
          400: "#4d7dff",
          500: "#2456f5",
          600: "#1a3fd1",
          700: "#1732a8",
          800: "#152a80",
          900: "#131f52",
        },
        surface: "#0b1220",
        panel: "#111a2e",
      },
    },
  },
  plugins: [],
};
