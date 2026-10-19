/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        mcd: {
          red: "#DA291C",
          redark: "#B01F14",
          yellow: "#FFC72C",
          dark: "#191919",
          ink: "#2B2B2B",
          mute: "#6B6B6B",
          cream: "#FFFBF3",
          line: "#EDE4D6",
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 12px 40px -12px rgba(25,25,25,0.18)",
        lift: "0 20px 50px -18px rgba(218,41,28,0.35)",
      },
      borderRadius: {
        blob: "28px",
      },
    },
  },
  plugins: [],
};
