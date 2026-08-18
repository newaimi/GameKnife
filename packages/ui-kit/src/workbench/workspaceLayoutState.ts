import { clampPanelWidth } from "./panelSizing.js";

export const WORKSPACE_LAYOUT_STORAGE_KEY = "gameknife-workspace-layout";
export const WORKSPACE_LEFT_MIN = 176;
export const WORKSPACE_LEFT_MAX = 320;
export const WORKSPACE_RIGHT_MIN = 260;
export const WORKSPACE_RIGHT_MAX = 440;

export type WorkspaceLayoutState = {
  leftWidth: number;
  rightWidth: number;
  leftCollapsed: boolean;
  rightCollapsed: boolean;
};

export const DEFAULT_WORKSPACE_LAYOUT: WorkspaceLayoutState = {
  leftWidth: 220,
  rightWidth: 320,
  leftCollapsed: false,
  rightCollapsed: false,
};

/**
 * Workbench layout is stored in the browser. Reads normalize legacy values, malformed JSON, and out-of-range widths.
 * Keeping localStorage access outside this helper lets component callers and unit tests reuse the same compatibility rules.
 */
export function readWorkspaceLayoutState(serialized: string | null): WorkspaceLayoutState {
  if (!serialized) return DEFAULT_WORKSPACE_LAYOUT;

  try {
    const value = JSON.parse(serialized) as Partial<WorkspaceLayoutState>;
    return {
      leftWidth: clampPanelWidth(readFiniteNumber(value.leftWidth, DEFAULT_WORKSPACE_LAYOUT.leftWidth), WORKSPACE_LEFT_MIN, WORKSPACE_LEFT_MAX),
      rightWidth: clampPanelWidth(readFiniteNumber(value.rightWidth, DEFAULT_WORKSPACE_LAYOUT.rightWidth), WORKSPACE_RIGHT_MIN, WORKSPACE_RIGHT_MAX),
      leftCollapsed: value.leftCollapsed === true,
      rightCollapsed: value.rightCollapsed === true,
    };
  } catch {
    return DEFAULT_WORKSPACE_LAYOUT;
  }
}

function readFiniteNumber(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
