export type ThemeMode = "light" | "dark";

export const THEME_STORAGE_KEY = "gameknife-theme";

/**
 * Theme parsing lives in the shared component package so every application shell uses the same storage key and
 * dark default, preventing theme mismatches or flashes during the first render.
 */
export function parseThemeMode(value: string | null | undefined): ThemeMode {
  return value === "light" || value === "dark" ? value : "dark";
}
