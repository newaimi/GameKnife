import { useEffect, useState } from "react";
import { DEFAULT_WORKSPACE_LAYOUT, readWorkspaceLayoutState, WORKSPACE_LAYOUT_STORAGE_KEY } from "./workspaceLayoutState.js";

/**
 * 面板状态按调用方提供的 gameknife 本地键独立保存。普通工具和专用编辑器共享读取规则，
 * 但可以使用不同键，防止一个页面的折叠操作改变另一个页面的工作习惯。
 */
export function useWorkspaceLayout(storageKey = WORKSPACE_LAYOUT_STORAGE_KEY) {
  const [layout, setLayout] = useState(() => {
    if (typeof window === "undefined") return DEFAULT_WORKSPACE_LAYOUT;
    try {
      return readWorkspaceLayoutState(window.localStorage.getItem(storageKey));
    } catch {
      return DEFAULT_WORKSPACE_LAYOUT;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(layout));
    } catch {
      // 禁用本地存储时保留当前会话状态，偏好持久化不能阻断编辑能力。
    }
  }, [layout, storageKey]);

  return [layout, setLayout] as const;
}
