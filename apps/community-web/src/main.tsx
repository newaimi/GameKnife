import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Link, BrowserRouter, Route, Routes } from "react-router-dom";
import { Settings, HelpCircle, ClipboardList, Home } from "lucide-react";
import { GameKnifeAppContext, communityContext } from "@gameknife/app-context";
import { gameKnifeApiClient } from "@gameknife/api-client";
import {
  AssetBoardWorkspace,
  CommunityHelpPage,
  CommunityJobsPage,
  CommunitySettingsPage,
  CommunityToolHome,
  ModelRequiredWorkspace,
  SequenceWorkspace,
  UpscaleWorkspace,
} from "@gameknife/image-workflows";
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
              <Route path="/jobs" element={<CommunityJobsPage />} />
              <Route path="/settings" element={<CommunitySettingsPage />} />
              <Route path="/help" element={<CommunityHelpPage />} />
              <Route path="/tools/background-remove" element={<ModelRequiredWorkspace title="去背景" />} />
              <Route path="/tools/upscale" element={<UpscaleWorkspace />} />
              <Route path="/tools/asset-board" element={<AssetBoardWorkspace />} />
              <Route path="/tools/sequence" element={<SequenceWorkspace />} />
              <Route path="/tools/video-generate" element={<ModelRequiredWorkspace title="AI生成视频" />} />
              <Route path="/tools/video-to-sequence" element={<ModelRequiredWorkspace title="视频转帧" />} />
              <Route path="/tools/character-rig" element={<ModelRequiredWorkspace title="骨骼拆分" />} />
              <Route path="/tools/sound-effect" element={<ModelRequiredWorkspace title="声效生成" />} />
              <Route path="/manual-edit" element={<ModelRequiredWorkspace title="手动编辑" />} />
              <Route path="*" element={<CommunityToolHome />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </GameKnifeAppContext.Provider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
