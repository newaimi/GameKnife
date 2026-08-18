export const supportedLanguages = ["en", "zh-CN"] as const;

export type SupportedLanguage = (typeof supportedLanguages)[number];

export const DEFAULT_LANGUAGE: SupportedLanguage = "en";
export const LANGUAGE_STORAGE_KEY = "gameknife-language";

export function normalizeLanguage(language?: string | null): SupportedLanguage {
  return language?.toLowerCase().startsWith("zh") ? "zh-CN" : DEFAULT_LANGUAGE;
}
