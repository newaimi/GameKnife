import type { EditorTool } from "@gameknife/editor-core";
import { useTranslation } from "react-i18next";
import { MANUAL_EDITOR_TOOLS } from "./manualEditorTools";

export function ManualEditorToolRail({ activeTool, onSelect }: { activeTool: EditorTool; onSelect: (tool: EditorTool) => void }) {
  const { t } = useTranslation("manualEditor");
  return (
    <aside className="manual-editor-tools" aria-label={t("tools.label")}>
      <h2>{t("tools.heading")}</h2>
      <div className="manual-editor-tool-list">
        {MANUAL_EDITOR_TOOLS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              className={`editor-tool-button ${activeTool === item.tool ? "active" : ""}`}
              type="button"
              data-tool={item.tool}
              aria-pressed={activeTool === item.tool}
              onClick={() => onSelect(item.tool)}
              key={item.tool}
            >
              <span className="editor-tool-icon">
                <Icon size={18} strokeWidth={2.5} />
              </span>
              <span className="editor-tool-title">{t(`tools.${item.translationKey}.label`)}</span>
              <em>{item.shortcut}</em>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
