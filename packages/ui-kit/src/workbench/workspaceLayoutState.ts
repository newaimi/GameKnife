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
 * 工作台布局保存在浏览器本地，读取时必须对旧版本、损坏 JSON 和超出范围的宽度做收敛。
 * 这里不直接访问 localStorage，便于 Community、Commercial 和单元测试复用同一份兼容规则。
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
