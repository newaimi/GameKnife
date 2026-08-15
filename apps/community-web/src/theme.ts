import { parseThemeMode, THEME_STORAGE_KEY, type ThemeMode } from "@gameknife/ui-kit";

export { THEME_STORAGE_KEY };
export type { ThemeMode };

export function readInitialTheme(): ThemeMode {
  return parseThemeMode(window.localStorage.getItem(THEME_STORAGE_KEY));
}

export function isTypingTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }

  const tagName = target.tagName.toLowerCase();
  return tagName === "input" || tagName === "textarea" || tagName === "select" || target.isContentEditable;
}
