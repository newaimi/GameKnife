import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Community keeps port 5174 so local testing and documentation use one stable entry point.
    // Binding to 0.0.0.0 allows devices on the same network to verify mobile layouts and touch interaction.
    host: "0.0.0.0",
    port: 5174,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
