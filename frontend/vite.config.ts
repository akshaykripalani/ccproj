import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: false,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: "charts",
              test: /node_modules[\\/](recharts|d3-|victory-|@reduxjs|redux|immer|reselect|decimal)/,
            },
            { name: "vendor", test: /node_modules/ },
          ],
        },
      },
    },
  },
});
