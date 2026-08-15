import type { CSSProperties, ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import {
  IconButton,
  PanelResizeHandle,
  useWorkspaceLayout,
  WORKSPACE_LEFT_MAX,
  WORKSPACE_LEFT_MIN,
  WORKSPACE_RIGHT_MAX,
  WORKSPACE_RIGHT_MIN,
} from "@gameknife/ui-kit";

const MANUAL_EDITOR_LAYOUT_STORAGE_KEY = "gameknife-manual-editor-layout";

export function ManualEditorLayout({ tools, stage, inspector }: { tools: ReactNode; stage: ReactNode; inspector: ReactNode }) {
  const [layout, setLayout] = useWorkspaceLayout(MANUAL_EDITOR_LAYOUT_STORAGE_KEY);
  const className = [
    "manual-editor-shell",
    layout.leftCollapsed ? "manual-editor-left-collapsed" : "",
    layout.rightCollapsed ? "manual-editor-right-collapsed" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const style = {
    "--manual-editor-left-width": `${layout.leftWidth}px`,
    "--manual-editor-right-width": `${layout.rightWidth}px`,
  } as CSSProperties;

  return (
    <section className={className} style={style}>
      {tools}
      <div className="manual-editor-divider manual-editor-divider-left">
        <PanelResizeHandle
          side="left"
          value={layout.leftWidth}
          min={WORKSPACE_LEFT_MIN}
          max={WORKSPACE_LEFT_MAX}
          label="调整编辑工具面板宽度"
          disabled={layout.leftCollapsed}
          onChange={(leftWidth) => setLayout((current) => ({ ...current, leftWidth }))}
        />
        <IconButton
          className="manual-editor-panel-toggle"
          label={layout.leftCollapsed ? "展开编辑工具面板" : "折叠编辑工具面板"}
          aria-expanded={!layout.leftCollapsed}
          onClick={() => setLayout((current) => ({ ...current, leftCollapsed: !current.leftCollapsed }))}
        >
          {layout.leftCollapsed ? <ChevronRight size={16} strokeWidth={2.5} /> : <ChevronLeft size={16} strokeWidth={2.5} />}
        </IconButton>
      </div>
      {stage}
      <div className="manual-editor-divider manual-editor-divider-right">
        <PanelResizeHandle
          side="right"
          value={layout.rightWidth}
          min={WORKSPACE_RIGHT_MIN}
          max={WORKSPACE_RIGHT_MAX}
          label="调整编辑检查器宽度"
          disabled={layout.rightCollapsed}
          onChange={(rightWidth) => setLayout((current) => ({ ...current, rightWidth }))}
        />
        <IconButton
          className="manual-editor-panel-toggle"
          label={layout.rightCollapsed ? "展开编辑检查器" : "折叠编辑检查器"}
          aria-expanded={!layout.rightCollapsed}
          onClick={() => setLayout((current) => ({ ...current, rightCollapsed: !current.rightCollapsed }))}
        >
          {layout.rightCollapsed ? <ChevronLeft size={16} strokeWidth={2.5} /> : <ChevronRight size={16} strokeWidth={2.5} />}
        </IconButton>
      </div>
      {inspector}
    </section>
  );
}
