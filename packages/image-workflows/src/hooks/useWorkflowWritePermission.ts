import { useGameKnifePermissions } from "@gameknife/app-context";

export function useWorkflowWritePermission(toolId: string) {
  const permissions = useGameKnifePermissions();
  // The backend groups workspace writes from public tools under jobs.create.
  // The frontend uses the same permission so PermissionProvider controls both tool entry and action buttons; Community allows it by default.
  return permissions.can("jobs.create", { tool_id: toolId });
}
