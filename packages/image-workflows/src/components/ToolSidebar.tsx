import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useGameKnifePermissions } from "@gameknife/app-context";
import { IconButton } from "@gameknife/ui-kit";
import { communityToolEntries, toolIconById } from "../tools/toolEntries";
import { readToolLinkProps } from "./toolLinkProps";

export function ToolSidebar({
  activeToolId,
  collapsed,
  onCollapsedChange,
}: {
  activeToolId: string;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
}) {
  const { t } = useTranslation("tools");
  const permissions = useGameKnifePermissions();

  return (
    <aside className="tool-panel" aria-label={t("panel")}>
      <div className="tool-panel-header">
        <h2>{t("panel")}</h2>
        <IconButton label={collapsed ? t("expandPanel") : t("collapsePanel")} aria-expanded={!collapsed} onClick={() => onCollapsedChange(!collapsed)}>
          {collapsed ? <ChevronRight size={16} strokeWidth={2.5} /> : <ChevronLeft size={16} strokeWidth={2.5} />}
        </IconButton>
      </div>
      {communityToolEntries.map((tool) => {
        const allowed = permissions.can(tool.permission, { tool_id: tool.id });
        const linkProps = readToolLinkProps(tool.openInNewTab);
        const label = t(`items.${tool.id}`, { defaultValue: tool.label });
        if (!allowed) {
          return (
            <span
              className="tool-button disabled"
              aria-disabled="true"
              aria-label={collapsed ? label : undefined}
              title={collapsed ? label : t("permissionDenied")}
              key={tool.id}
            >
              <span className="tool-icon">{toolIconById[tool.id]}</span>
              <span className="tool-title">{label}</span>
              <em>{tool.badge}</em>
            </span>
          );
        }

        return (
          <NavLink
            className={`tool-button ${tool.id === activeToolId ? "active" : ""}`}
            to={tool.route}
            target={linkProps.target}
            rel={linkProps.rel}
            aria-label={collapsed ? label : undefined}
            title={collapsed ? label : undefined}
            key={tool.id}
          >
            <span className="tool-icon">{toolIconById[tool.id]}</span>
            <span className="tool-title">{label}</span>
            <em>{tool.badge}</em>
          </NavLink>
        );
      })}
    </aside>
  );
}
