import { useEffect, useState } from "react";
import { DEFAULT_WORKSPACE_LAYOUT, readWorkspaceLayoutState, WORKSPACE_LAYOUT_STORAGE_KEY } from "./workspaceLayoutState.js";

/**
 * Persists panel state under a caller-provided GameKnife key. Workbenches share the storage rules while using
 * independent keys so collapse choices never leak between tools and dedicated editors.
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
      // Keep the in-session state if storage is unavailable; preference persistence must not block editing.
    }
  }, [layout, storageKey]);

  return [layout, setLayout] as const;
}
