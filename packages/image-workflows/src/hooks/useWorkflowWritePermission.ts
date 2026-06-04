import { useGameKnifePermissions } from "@gameknife/app-context";

export function useWorkflowWritePermission(toolId: string) {
  const permissions = useGameKnifePermissions();
  // 后端把公共工具的项目内写操作统一归到 jobs.create。
  // 前端沿用同一个权限名，商业版注入 RBAC 后可以同时控制入口和按钮，Community 默认放行。
  return permissions.can("jobs.create", { tool_id: toolId });
}
