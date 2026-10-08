import type { ReactNode } from "react";
import { Link } from "react-router";
import { Languages } from "lucide-react";
import { otherLang, useI18n } from "../i18n";
import { Logo, LogoMark } from "./Logo";
import ThemeToggle from "./ThemeToggle";

export default function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  const { t, lang, toggleLang } = useI18n();
  return (
    <div className="min-h-dvh bg-surface lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <div className="flex min-h-dvh flex-col px-4 sm:px-8 lg:px-12">
        <header className="flex h-16 items-center justify-between lg:h-20">
          <Link to="/" aria-label={t.landing.nav.home} className="rounded-lg">
            <Logo />
          </Link>
          <div className="flex items-center gap-1">
            <ThemeToggle className="size-10 justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-ink-950" />
            <button
              type="button"
              onClick={toggleLang}
              className="inline-flex h-10 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-ink-950"
            >
              <Languages className="size-4" aria-hidden />
              <span lang={otherLang(lang)}>{t.otherLang}</span>
            </button>
          </div>
        </header>

        <main className="flex flex-1 items-center justify-center py-10">
          <div className="animate-pop-in w-full max-w-sm">
            <h1 className="text-2xl font-extrabold text-ink-950 sm:text-3xl">{title}</h1>
            <p className="mt-2 text-slate-500">{subtitle}</p>
            <div className="mt-8">{children}</div>
            <p className="mt-6 text-sm text-slate-600">{footer}</p>
          </div>
        </main>

        <footer className="flex flex-wrap gap-x-5 gap-y-2 py-6 text-xs text-slate-400">
          <Link to="/privacy" className="transition-colors hover:text-slate-600">
            {t.legal.privacy}
          </Link>
          <Link to="/terms" className="transition-colors hover:text-slate-600">
            {t.legal.terms}
          </Link>
        </footer>
      </div>

      <BrandPanel />
    </div>
  );
}

function BrandPanel() {
  const { t } = useI18n();
  const c = t.landing.chat;
  return (
    <aside className="relative hidden overflow-hidden bg-brand-600 text-white lg:flex lg:items-center lg:justify-center">
      <div aria-hidden className="dot-grid absolute inset-0 [mask-image:radial-gradient(ellipse_80%_70%_at_50%_40%,black,transparent)]" />
      <div className="relative w-full max-w-md px-10 py-16">
        <LogoMark px={56} className="shadow-float ring-2 ring-white/25" />
        <p className="t-h2 mt-8 text-balance">{t.tagline}</p>
        <ul aria-label={t.landing.hero.rolesLabel} className="mt-6 flex flex-wrap gap-2">
          {t.landing.hero.roles.map((role) => (
            <li key={role} className="rounded-full bg-white/10 px-3.5 py-1.5 text-sm font-semibold ring-1 ring-white/20">
              {role}
            </li>
          ))}
        </ul>
        <div aria-hidden className="mt-10 space-y-2.5 rounded-2xl bg-surface p-4 text-[13.5px] leading-6 text-ink-900 shadow-float">
          <p className="animate-msg-in w-fit max-w-[85%] rounded-2xl rounded-ss-md bg-slate-100 px-3.5 py-2 [animation-delay:400ms]">{c.m1}</p>
          <p className="animate-msg-in ms-auto w-fit max-w-[85%] rounded-2xl rounded-se-md bg-brand-600 px-3.5 py-2 text-white [animation-delay:1100ms]">{c.m2}</p>
        </div>
      </div>
    </aside>
  );
}
