export type ThemeMode = "light" | "dark";

export const THEME_STORAGE_KEY = "gameknife-theme";

/**
 * 主题读取集中在公共组件包，Community 与 Commercial 使用同一存储键和暗色默认值，
 * 避免两个入口在首次渲染时出现不同主题或闪烁。
 */
export function parseThemeMode(value: string | null | undefined): ThemeMode {
  return value === "light" || value === "dark" ? value : "dark";
}
