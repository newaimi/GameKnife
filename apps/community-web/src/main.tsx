import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import { createGameKnifeI18n } from "@gameknife/i18n";
import { App } from "./App";
import { readInitialTheme } from "./theme";
import "@gameknife/image-workflows/styles.css";
import "./styles.css";

// Set the theme before React's first render so the dark-default workbench never flashes light tokens.
document.documentElement.dataset.theme = readInitialTheme();

async function bootstrap() {
  const i18n = await createGameKnifeI18n();

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <I18nextProvider i18n={i18n}>
        <App />
      </I18nextProvider>
    </StrictMode>,
  );
}

void bootstrap();
