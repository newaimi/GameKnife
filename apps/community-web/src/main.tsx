import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Link, BrowserRouter, Route, Routes } from "react-router-dom";
import { Settings, HelpCircle, ClipboardList, Home } from "lucide-react";
import { GameKnifeAppContext, communityContext } from "@gameknife/app-context";
import { gameKnifeApiClient } from "@gameknife/api-client";
import { CommunityToolHome } from "@gameknife/image-workflows";
import type { AppContext } from "@gameknife/shared-types";
import "./styles.css";

function App() {
  const [appContext, setAppContext] = useState<AppContext>(communityContext);

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

  return (
    <GameKnifeAppContext.Provider value={appContext}>
      <BrowserRouter>
        <div className="app-shell">
          <header className="topbar">
            <Link className="brand" to="/">
              GameKnife
              <span>游戏刀工坊</span>
            </Link>
            <nav className="nav">
              <Link to="/">
                <Home size={18} />
                首页
              </Link>
              <Link to="/jobs">
                <ClipboardList size={18} />
                任务
              </Link>
              <Link to="/settings">
                <Settings size={18} />
                设置
              </Link>
              <Link to="/help">
                <HelpCircle size={18} />
                帮助
              </Link>
            </nav>
          </header>
          <main className="content">
            <Routes>
              <Route path="/" element={<CommunityToolHome />} />
              <Route path="/jobs" element={<Placeholder title="任务" />} />
              <Route path="/settings" element={<Placeholder title="设置" />} />
              <Route path="/help" element={<Placeholder title="帮助" />} />
              <Route path="*" element={<CommunityToolHome />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </GameKnifeAppContext.Provider>
  );
}

function Placeholder({ title }: { title: string }) {
  return <section className="placeholder">{title}</section>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
