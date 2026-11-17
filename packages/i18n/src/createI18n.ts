import { createInstance, type i18n as I18nInstance } from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";
import { DEFAULT_LANGUAGE, LANGUAGE_STORAGE_KEY, normalizeLanguage, supportedLanguages, type SupportedLanguage } from "./languages.js";
import { namespaces, resources } from "./resources.js";

export type CreateGameKnifeI18nOptions = {
  initialLanguage?: SupportedLanguage | string;
  detectLanguage?: boolean;
};

export async function createGameKnifeI18n(options: CreateGameKnifeI18nOptions = {}): Promise<I18nInstance> {
  const instance = createInstance();
  const detectLanguage = options.detectLanguage ?? typeof window !== "undefined";

  if (detectLanguage) {
    instance.use(LanguageDetector);
  }
  instance.use(initReactI18next);

  await instance.init({
    resources,
    ns: [...namespaces],
    defaultNS: "common",
    supportedLngs: [...supportedLanguages],
    fallbackLng: DEFAULT_LANGUAGE,
    load: "currentOnly",
    showSupportNotice: false,
    lng: options.initialLanguage ? normalizeLanguage(options.initialLanguage) : detectLanguage ? undefined : DEFAULT_LANGUAGE,
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ["localStorage"],
      caches: ["localStorage"],
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
      convertDetectedLanguage: normalizeLanguage,
    },
  });

  syncDocumentLanguage(instance);
  return instance;
}

function syncDocumentLanguage(instance: I18nInstance) {
  if (typeof document === "undefined") return;

  const applyLanguage = (language: string) => {
    const normalizedLanguage = normalizeLanguage(language);
    document.documentElement.lang = normalizedLanguage;
    document.documentElement.dir = instance.dir(normalizedLanguage);
  };

  applyLanguage(instance.resolvedLanguage ?? instance.language);
  instance.on("languageChanged", applyLanguage);
}
