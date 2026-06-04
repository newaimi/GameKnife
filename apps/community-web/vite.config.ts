import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // 社区版开发地址沿用原工程的 5174，用户本地测试和文档都以这个端口为入口。
    // host 使用 0.0.0.0，方便同一局域网设备验证移动端布局和触控交互。
    host: "0.0.0.0",
    port: 5174,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
