import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import en from "./en";
import ar, { type Dict } from "./ar";
import { makeFormat, type Format } from "../lib/format";

export type Lang = "en" | "ar";

const dicts: Record<Lang, Dict> = { en, ar };
const STORAGE_KEY = "dm.lang";

type I18n = { lang: Lang; dir: "rtl" | "ltr"; t: Dict; f: Format; setLang: (l: Lang) => void; toggleLang: () => void };

const I18nContext = createContext<I18n | null>(null);

const isLang = (v: string | null): v is Lang => v === "en" || v === "ar";

/** The language a link to the other language switches to. */
export const otherLang = (l: Lang): Lang => (l === "en" ? "ar" : "en");

function initialLang(): Lang {
  const fromUrl = new URLSearchParams(location.search).get("lang");
  if (isLang(fromUrl)) return fromUrl;
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (isLang(saved)) return saved;
  } catch {
    // storage unavailable
  }
  return "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const dir = lang === "ar" ? "rtl" : "ltr";

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
  }, [lang, dir]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      // storage unavailable
    }
  }, []);

  const value = useMemo<I18n>(
    () => ({
      lang,
      dir,
      t: dicts[lang],
      f: makeFormat(lang, dicts[lang]),
      setLang,
      toggleLang: () => setLang(otherLang(lang)),
    }),
    [lang, dir, setLang],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  return ctx;
}
