import type { ReactNode } from "react";
import { Link } from "react-router";
import { Languages } from "lucide-react";
import { otherLang, useI18n } from "../i18n";
import { Logo } from "./Logo";
import ThemeToggle from "./ThemeToggle";

/** Login/sign-up frame: one centred card on the grey canvas, a quiet header and footer. */
export default function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  const { t, lang, toggleLang } = useI18n();
  return (
    <div className="relative flex min-h-dvh flex-col bg-canvas px-4 sm:px-8">
      <div aria-hidden className="line-grid pointer-events-none absolute inset-x-0 top-0 h-80 [mask-image:linear-gradient(to_bottom,black,transparent)]" />
      <header className="relative flex h-16 items-center justify-between">
        <Link to="/" aria-label={t.landing.nav.home} className="rounded-lg">
          <Logo />
        </Link>
        <div className="flex items-center gap-1">
          <ThemeToggle className="size-10 justify-center rounded-lg text-slate-500 hover:bg-fill hover:text-ink-950" />
          <button
            type="button"
            onClick={toggleLang}
            className="inline-flex h-10 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-slate-500 transition-colors hover:bg-fill hover:text-ink-950"
          >
            <Languages className="size-4" aria-hidden />
            <span lang={otherLang(lang)}>{t.otherLang}</span>
          </button>
        </div>
      </header>

      <main className="relative flex flex-1 items-start justify-center py-8 sm:items-center sm:py-12">
        <div className="w-full max-w-[26rem]">
          <div className="rounded-xl border border-slate-200 bg-surface p-6 shadow-lift sm:p-8">
            <h1 className="text-[1.375rem] font-semibold tracking-tight text-ink-950">{title}</h1>
            <p className="mt-1.5 text-sm leading-6 text-slate-500">{subtitle}</p>
            <div className="mt-6">{children}</div>
          </div>
          <p className="mt-5 text-center text-sm text-slate-600">{footer}</p>
        </div>
      </main>

      <footer className="relative flex flex-wrap justify-center gap-x-5 gap-y-2 py-6 text-xs text-slate-400">
        <Link to="/privacy" className="transition-colors hover:text-slate-600">
          {t.legal.privacy}
        </Link>
        <Link to="/terms" className="transition-colors hover:text-slate-600">
          {t.legal.terms}
        </Link>
      </footer>
    </div>
  );
}
