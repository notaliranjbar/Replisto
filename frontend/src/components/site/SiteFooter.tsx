import type { ReactNode } from "react";
import { Link } from "react-router";
import { Languages } from "lucide-react";
import { useAuth } from "../../auth/AuthContext";
import { otherLang, useI18n } from "../../i18n";
import { Logo } from "../Logo";
import { SECTIONS } from "./SiteHeader";

const SUPPORT_EMAIL: string | undefined = import.meta.env.VITE_SUPPORT_EMAIL;

export default function SiteFooter({ onLanding = false }: { onLanding?: boolean }) {
  const { t, lang, toggleLang } = useI18n();
  const { loggedIn } = useAuth();
  const L = t.landing;
  const year = new Intl.DateTimeFormat(lang === "ar" ? "ar" : "en-US", { year: "numeric" }).format(new Date());
  const sectionLabels = { try: L.nav.try, features: L.nav.features, how: L.nav.how, pricing: L.nav.pricing, faq: L.nav.faq };

  return (
    <footer className="bg-night-950 text-white/70">
      <div className="container-site grid grid-cols-2 gap-x-6 gap-y-10 py-14 sm:grid-cols-3 lg:grid-cols-[minmax(0,1.6fr)_repeat(3,minmax(0,1fr))] lg:py-16">
        <div className="col-span-2 max-w-xs sm:col-span-3 lg:col-span-1">
          <Logo tone="dark" />
          <p className="mt-4 text-sm leading-7">{L.footer.about}</p>
          <button
            type="button"
            onClick={toggleLang}
            className="mt-5 inline-flex h-10 items-center gap-2 rounded-lg border border-white/15 px-3.5 text-sm font-medium text-white/85 transition-colors hover:border-white/35 hover:text-white"
          >
            <Languages className="size-4" aria-hidden />
            <span lang={otherLang(lang)}>{t.otherLang}</span>
          </button>
        </div>

        {/* for a logged-in user "/" is the dashboard, so there are no sections to link to */}
        {!loggedIn && (
          <FooterCol title={L.footer.product}>
            {SECTIONS.map((id) =>
              onLanding ? (
                <a key={id} href={`#${id}`} className={linkCls}>
                  {sectionLabels[id]}
                </a>
              ) : (
                <Link key={id} to={`/#${id}`} className={linkCls}>
                  {sectionLabels[id]}
                </Link>
              ),
            )}
          </FooterCol>
        )}

        <FooterCol title={L.footer.account}>
          {loggedIn ? (
            <Link to="/" className={linkCls}>
              {L.nav.openPanel}
            </Link>
          ) : (
            <>
              <Link to="/register" className={linkCls}>
                {L.nav.start}
              </Link>
              <Link to="/login" className={linkCls}>
                {L.nav.login}
              </Link>
            </>
          )}
          {SUPPORT_EMAIL && (
            <a href={`mailto:${SUPPORT_EMAIL}`} className={linkCls}>
              {L.footer.support}
            </a>
          )}
        </FooterCol>

        <FooterCol title={L.footer.legal}>
          <Link to="/privacy" className={linkCls}>
            {t.legal.privacy}
          </Link>
          <Link to="/terms" className={linkCls}>
            {t.legal.terms}
          </Link>
          <Link to="/data-deletion" className={linkCls}>
            {t.legal.dataDeletion}
          </Link>
        </FooterCol>
      </div>
      <div className="border-t border-white/10">
        <div className="container-site flex flex-wrap items-center justify-between gap-3 py-6 text-xs text-white/50">
          <span>{L.footer.rights(year)}</span>
          <span>{t.tagline}</span>
        </div>
      </div>
    </footer>
  );
}

const linkCls = "w-fit py-1 text-sm transition-colors hover:text-white";

function FooterCol({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h2 className="mb-3 text-sm font-bold text-white">{title}</h2>
      <nav aria-label={title} className="flex flex-col gap-1.5">
        {children}
      </nav>
    </div>
  );
}
