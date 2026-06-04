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

// Community 默认提供匿名上下文，避免工具页面各自判断空用户。
// 商用版会在外壳层注入真实上下文，公共工具只读取统一接口。
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
  // Community 不需要真实用户权限，默认放行可以保持无登录工具体验。
  // Studio 从外壳注入 RBAC 权限，公共工具只读这个接口，避免导入商用用户和角色类型。
  return <GameKnifePermissionContext.Provider value={value ?? allowAllPermissions}>{children}</GameKnifePermissionContext.Provider>;
}

export function useGameKnifePermissions(): PermissionProviderValue {
  return useContext(GameKnifePermissionContext);
}
