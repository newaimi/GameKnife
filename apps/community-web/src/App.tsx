import { Suspense, useCallback, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { GameKnifeAppContext, communityContext } from "@gameknife/app-context";
import { gameKnifeApiClient } from "@gameknife/api-client";
import {
  CommunityHelpPage,
  CommunityJobsPage,
  CommunitySettingsPage,
  ImageAssetSessionProvider,
  communityWorkflowRoutes,
} from "@gameknife/image-workflows";
import type { AppContext } from "@gameknife/shared-types";
import { CommunityShell } from "./CommunityShell";
import { isTypingTarget, readInitialTheme, THEME_STORAGE_KEY, type ThemeMode } from "./theme";

export function App() {
  const [appContext, setAppContext] = useState<AppContext>(communityContext);
  const [theme, setTheme] = useState<ThemeMode>(() => readInitialTheme());
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const toggleTheme = useCallback(() => {
    setTheme((current) => (current === "light" ? "dark" : "light"));
  }, []);

  useEffect(() => {
    let alive = true;
    gameKnifeApiClient
      .getContext()
      .then((context) => {
        if (alive) {
          setAppContext(context);
        }
      })
      .catch(() => {
        if (alive) {
          setAppContext(communityContext);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    // Theme variables live on html, so existing CSS variables switch together with data-theme.
    // Community persists the selection so refreshing a local tool does not discard the preferred color mode.
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    const handleThemeShortcut = (event: KeyboardEvent) => {
      if (event.repeat || event.metaKey || event.ctrlKey || event.altKey || isTypingTarget(event.target)) {
        return;
      }
      if (event.key.toLowerCase() !== "t") {
        return;
      }

      event.preventDefault();
      toggleTheme();
    };

    window.addEventListener("keydown", handleThemeShortcut);
    return () => window.removeEventListener("keydown", handleThemeShortcut);
  }, [toggleTheme]);

  return (
    <GameKnifeAppContext.Provider value={appContext}>
      <BrowserRouter>
        <CommunityShell
          theme={theme}
          mobileMenuOpen={mobileMenuOpen}
          onMobileMenuToggle={() => setMobileMenuOpen((open) => !open)}
          onMobileMenuClose={() => setMobileMenuOpen(false)}
          onThemeToggle={toggleTheme}
        >
          <main className="content">
            {/* The Community shell composes public routes and global providers. The public package owns the image-asset session so tool changes preserve workbench state. */}
            <ImageAssetSessionProvider>
              <Suspense fallback={<div className="page-panel">加载中</div>}>
                <Routes>
                  <Route path="/" element={<Navigate to="/tools/background-remove" replace />} />
                  <Route path="/jobs" element={<CommunityJobsPage />} />
                  <Route path="/settings" element={<CommunitySettingsPage />} />
                  <Route path="/help" element={<CommunityHelpPage />} />
                  {communityWorkflowRoutes.map((route) => {
                    const FeatureComponent = route.component;
                    return <Route key={route.id} path={route.path} element={<FeatureComponent />} />;
                  })}
                  <Route path="*" element={<Navigate to="/tools/background-remove" replace />} />
                </Routes>
              </Suspense>
            </ImageAssetSessionProvider>
          </main>
        </CommunityShell>
      </BrowserRouter>
    </GameKnifeAppContext.Provider>
  );
}
