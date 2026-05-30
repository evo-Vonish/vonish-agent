export type Locale = "en-US" | "zh-CN" | "ja-JP" | "ko-KR" | "fr-FR" | "de-DE";

export interface LanguageProfile {
  locale: Locale;
  label: string;
  nativeLabel: string;
  direction: "ltr" | "rtl";
  tone: string[];
  avoid: string[];
  systemStyleHint: string;
}

export type I18nDictionary = Record<string, string>;
