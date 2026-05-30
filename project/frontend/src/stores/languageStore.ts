import { create } from "zustand";
import type { Locale } from "@/i18n/types";

const LS_KEY = "vonish-agent.locale";

function loadLocale(): Locale {
  try {
    const stored = localStorage.getItem(LS_KEY);
    if (stored && ["en-US", "zh-CN", "ja-JP", "ko-KR", "fr-FR", "de-DE"].includes(stored)) {
      return stored as Locale;
    }
  } catch {}
  // Auto-detect browser language
  const nav = navigator.language;
  if (nav.startsWith("zh")) return "zh-CN";
  if (nav.startsWith("ja")) return "ja-JP";
  if (nav.startsWith("ko")) return "ko-KR";
  if (nav.startsWith("fr")) return "fr-FR";
  if (nav.startsWith("de")) return "de-DE";
  return "en-US";
}

interface LanguageState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

export const useLanguageStore = create<LanguageState>((set) => ({
  locale: loadLocale(),
  setLocale: (locale: Locale) => {
    try {
      localStorage.setItem(LS_KEY, locale);
    } catch {}
    set({ locale });
  },
}));
