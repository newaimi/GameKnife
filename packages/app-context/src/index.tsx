import { createContext, useContext, type ReactNode } from "react";
import type { AppContext } from "@gameknife/shared-types";

export const communityContext: AppContext = {
  principal: {
    id: "anonymous",
    kind: "anonymous",
    displayName: "本地用户",
  },
  workspace: {
    id: "local",
    kind: "local",
    name: "本地工作区",
  },
  capabilities: {
    edition: "community",
    features: [],
  },
};

// Community provides an anonymous context so tool pages never need their own missing-user fallback.
// Other application shells may inject an explicit principal and workspace through the provider while public tools consume one stable interface.
export const GameKnifeAppContext = createContext<AppContext>(communityContext);

export function useGameKnifeAppContext(): AppContext {
  return useContext(GameKnifeAppContext);
}

export interface PermissionProviderValue {
  can: (action: string, resource?: unknown) => boolean;
  require: (action: string, resource?: unknown) => void;
}

const allowAllPermissions: PermissionProviderValue = {
  can: () => true,
  require: () => undefined,
};

export const GameKnifePermissionContext = createContext<PermissionProviderValue>(allowAllPermissions);

export function PermissionProvider({ value, children }: { value?: PermissionProviderValue; children: ReactNode }) {
  // Community keeps its login-free workflow by allowing actions through the default implementation.
  // Callers that enforce permissions inject their checker through the provider, so public tools never import account or role types.
  return <GameKnifePermissionContext.Provider value={value ?? allowAllPermissions}>{children}</GameKnifePermissionContext.Provider>;
}

export function useGameKnifePermissions(): PermissionProviderValue {
  return useContext(GameKnifePermissionContext);
}
