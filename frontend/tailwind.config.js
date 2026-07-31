/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      keyframes: {
        twinkle: {
          "0%, 100%": { opacity: "0.15", transform: "translate(0, 0) scale(0.85)" },
          "50%": {
            opacity: "1",
            transform: "translate(var(--dx, 4px), var(--dy, -4px)) scale(1.1)",
          },
        },
        drift: {
          "0%": { transform: "translate(0, 0)" },
          "50%": { transform: "translate(-2%, 2%)" },
          "100%": { transform: "translate(0, 0)" },
        },
      },
      animation: {
        twinkle: "twinkle 4s ease-in-out infinite",
        drift: "drift 20s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
