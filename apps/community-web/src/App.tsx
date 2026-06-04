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
    // 主题变量定义在 html 上，原工程的 CSS 变量会跟随 data-theme 同步切换。
    // Community 仍保存用户选择，避免本地工具刷新后丢失常用的亮暗色偏好。
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
            {/* Community Shell 只装配公共能力；图片素材会话放在公共包里，商业版也通过同一入口复用工作台状态。 */}
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
