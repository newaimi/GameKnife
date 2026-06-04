import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "@gameknife/image-workflows/styles.css";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
