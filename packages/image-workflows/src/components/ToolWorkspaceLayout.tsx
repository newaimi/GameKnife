import type { CSSProperties, ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import {
  IconButton,
  PanelResizeHandle,
  useWorkspaceLayout,
  WORKSPACE_LAYOUT_STORAGE_KEY,
  WORKSPACE_LEFT_MAX,
  WORKSPACE_LEFT_MIN,
  WORKSPACE_RIGHT_MAX,
  WORKSPACE_RIGHT_MIN,
} from "@gameknife/ui-kit";
import { ToolSidebar } from "./ToolSidebar";

export function ToolWorkspaceLayout({ activeToolId, children }: { activeToolId: string; children: ReactNode }) {
  const [layout, setLayout] = useWorkspaceLayout(WORKSPACE_LAYOUT_STORAGE_KEY);

  const workspaceClassName = [
    "workspace",
    layout.leftCollapsed ? "workspace-left-collapsed" : "",
    layout.rightCollapsed ? "workspace-right-collapsed" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const workspaceStyle = {
    "--workspace-left-width": `${layout.leftWidth}px`,
    "--workspace-right-width": `${layout.rightWidth}px`,
  } as CSSProperties;

  return (
    // 工作台外壳统一承载预览底层、悬浮工具面板和参数面板，保证 Community 与 Studio
    // 复用同一套折叠、拖宽和高度约束。具体预览、参数和任务状态仍由各工具自己维护，
    // 避免公共布局反向绑定某个工具流程。
    <section className={workspaceClassName} style={workspaceStyle}>
      <ToolSidebar
        activeToolId={activeToolId}
        collapsed={layout.leftCollapsed}
        onCollapsedChange={(leftCollapsed) => setLayout((current) => ({ ...current, leftCollapsed }))}
      />
      <div className="workspace-divider workspace-divider-left">
        <PanelResizeHandle
          side="left"
          value={layout.leftWidth}
          min={WORKSPACE_LEFT_MIN}
          max={WORKSPACE_LEFT_MAX}
          label="调整工具面板宽度"
          disabled={layout.leftCollapsed}
          onChange={(leftWidth) => setLayout((current) => ({ ...current, leftWidth }))}
        />
      </div>
      {children}
      <div className="workspace-divider workspace-divider-right">
        <PanelResizeHandle
          side="right"
          value={layout.rightWidth}
          min={WORKSPACE_RIGHT_MIN}
          max={WORKSPACE_RIGHT_MAX}
          label="调整参数面板宽度"
          disabled={layout.rightCollapsed}
          onChange={(rightWidth) => setLayout((current) => ({ ...current, rightWidth }))}
        />
        <IconButton
          className="workspace-right-toggle"
          label={layout.rightCollapsed ? "展开参数面板" : "折叠参数面板"}
          aria-expanded={!layout.rightCollapsed}
          onClick={() => setLayout((current) => ({ ...current, rightCollapsed: !current.rightCollapsed }))}
        >
          {layout.rightCollapsed ? <ChevronLeft size={16} strokeWidth={2.5} /> : <ChevronRight size={16} strokeWidth={2.5} />}
        </IconButton>
      </div>
    </section>
  );
}
