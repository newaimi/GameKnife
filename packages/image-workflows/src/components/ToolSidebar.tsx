import { NavLink } from "react-router-dom";
import { useGameKnifePermissions } from "@gameknife/app-context";
import { communityToolEntries, toolIconById } from "../tools/toolEntries";

export function ToolSidebar({ activeToolId }: { activeToolId: string }) {
  const permissions = useGameKnifePermissions();

  return (
    <aside className="tool-panel">
      <h2>资源工具</h2>
      {communityToolEntries.map((tool) => {
        const allowed = permissions.can(tool.permission, { tool_id: tool.id });
        if (!allowed) {
          return (
            <span className="tool-button disabled" aria-disabled="true" title="当前项目没有使用此工具的权限" key={tool.id}>
              <span className="tool-icon">{toolIconById[tool.id]}</span>
              <span className="tool-title">{tool.label}</span>
              <em>{tool.badge}</em>
            </span>
          );
        }

        return (
          <NavLink className={`tool-button ${tool.id === activeToolId ? "active" : ""}`} to={tool.route} key={tool.id}>
            <span className="tool-icon">{toolIconById[tool.id]}</span>
            <span className="tool-title">{tool.label}</span>
            <em>{tool.badge}</em>
          </NavLink>
        );
      })}
    </aside>
  );
}
