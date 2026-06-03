import { createContext, useContext } from "react";
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
