import { NavLink } from "react-router-dom";
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
  const permissions = useGameKnifePermissions();

  return (
    <aside className="tool-panel" aria-label="资源工具">
      <div className="tool-panel-header">
        <h2>资源工具</h2>
        <IconButton label={collapsed ? "展开工具面板" : "折叠工具面板"} aria-expanded={!collapsed} onClick={() => onCollapsedChange(!collapsed)}>
          {collapsed ? <ChevronRight size={16} strokeWidth={2.5} /> : <ChevronLeft size={16} strokeWidth={2.5} />}
        </IconButton>
      </div>
      {communityToolEntries.map((tool) => {
        const allowed = permissions.can(tool.permission, { tool_id: tool.id });
        const linkProps = readToolLinkProps(tool.openInNewTab);
        if (!allowed) {
          return (
            <span
              className="tool-button disabled"
              aria-disabled="true"
              aria-label={collapsed ? tool.label : undefined}
              title={collapsed ? tool.label : "当前项目没有使用此工具的权限"}
              key={tool.id}
            >
              <span className="tool-icon">{toolIconById[tool.id]}</span>
              <span className="tool-title">{tool.label}</span>
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
            aria-label={collapsed ? tool.label : undefined}
            title={collapsed ? tool.label : undefined}
            key={tool.id}
          >
            <span className="tool-icon">{toolIconById[tool.id]}</span>
            <span className="tool-title">{tool.label}</span>
            <em>{tool.badge}</em>
          </NavLink>
        );
      })}
    </aside>
  );
}
