import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { readInitialTheme } from "./theme";
import "@gameknife/image-workflows/styles.css";
import "./styles.css";

// Set the theme before React's first render so the dark-default workbench never flashes light tokens.
document.documentElement.dataset.theme = readInitialTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
