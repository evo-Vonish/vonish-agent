import { useCallback } from "react";
import { useLanguageStore } from "@/stores/languageStore";
import { profiles } from "./profiles";
import enUS from "./dictionaries/en-US";
import zhCN from "./dictionaries/zh-CN";
import jaJP from "./dictionaries/ja-JP";
import koKR from "./dictionaries/ko-KR";
import frFR from "./dictionaries/fr-FR";
import deDE from "./dictionaries/de-DE";
import type { I18nDictionary, Locale } from "./types";

const dictionaries: Record<Locale, I18nDictionary> = {
  "en-US": enUS,
  "zh-CN": zhCN,
  "ja-JP": jaJP,
  "ko-KR": koKR,
  "fr-FR": frFR,
  "de-DE": deDE,
};

const isDev = import.meta.env.DEV;

/**
 * Translate a key to the current locale.
 * Falls back to en-US if missing; warns in dev mode.
 */
export function translate(key: string, locale: Locale, params?: Record<string, string | number>): string {
  const dict = dictionaries[locale] ?? dictionaries["en-US"];
  let text = dict[key];
  if (text === undefined) {
    if (isDev) console.warn(`[i18n] Missing key "${key}" for locale "${locale}"`);
    text = dictionaries["en-US"][key] ?? key;
  }
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(`{${k}}`, String(v));
    }
  }
  return text;
}

export function useI18n() {
  const locale = useLanguageStore((s) => s.locale);
  const profile = profiles[locale] ?? profiles["en-US"];

  const t = useCallback(
    (key: string, params?: Record<string, string | number>) => translate(key, locale, params),
    [locale],
  );

  return { t, locale, profile };
}
