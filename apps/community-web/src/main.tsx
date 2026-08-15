import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { readInitialTheme } from "./theme";
import "@gameknife/image-workflows/styles.css";
import "./styles.css";

// 在 React 首次渲染前设置主题，避免暗色默认工作台先短暂显示亮色令牌。
document.documentElement.dataset.theme = readInitialTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
