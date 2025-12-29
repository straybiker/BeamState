/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                primary: "#3b82f6",
                secondary: "#64748b",
                success: "#22c55e",
                danger: "#ef4444",
                background: "#0f172a",
                surface: "#1e293b",
            }
        },
    },
    plugins: [],
}
