import type { ReactNode } from "react";
import { ToolSidebar } from "./ToolSidebar";

export function ToolWorkspaceLayout({ activeToolId, children }: { activeToolId: string; children: ReactNode }) {
  return (
    // 三栏外壳在所有工具里一致，抽到这里可以保证 Community 和 Studio 复用同一套导航与高度约束。
    // 具体预览、参数和任务状态仍由各工具自己维护，避免公共布局反向绑定某个工具流程。
    <section className="workspace">
      <ToolSidebar activeToolId={activeToolId} />
      {children}
    </section>
  );
}
