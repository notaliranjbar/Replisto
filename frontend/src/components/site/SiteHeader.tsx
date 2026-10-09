import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { ArrowRight, Languages, Menu, X } from "lucide-react";
import { useAuth } from "../../auth/AuthContext";
import { otherLang, useI18n } from "../../i18n";
import { Logo } from "../Logo";
import ThemeToggle from "../ThemeToggle";
import { buttonClass, cx } from "../ui";

export const SECTIONS = ["try", "features", "how", "pricing", "faq"] as const;

/**
 * Public site header. Over a coloured hero it starts transparent with white text and turns
 * solid once the page scrolls; elsewhere (`overHero` off) it is always solid.
 */
export default function SiteHeader({ overHero = false }: { overHero?: boolean }) {
  const { t, lang, toggleLang } = useI18n();
  const { loggedIn } = useAuth();
  const L = t.landing.nav;
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!overHero) return;
    let frame = 0;
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setScrolled(window.scrollY > 8));
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
    };
  }, [overHero]);

  const light = overHero && !scrolled; // white text on the coloured hero
  const labels: Record<(typeof SECTIONS)[number], string> = { try: L.try, features: L.features, how: L.how, pricing: L.pricing, faq: L.faq };
  // the landing sections only exist for visitors; for a logged-in user "/" is the dashboard
  const sections = loggedIn ? [] : SECTIONS;
  const switchTo = otherLang(lang);

  return (
    <header
      className={cx(
        "sticky top-0 z-40 transition-[background-color,border-color,box-shadow] duration-300",
        light ? "border-b border-transparent bg-night-950" : "border-b border-slate-200 bg-surface/85 backdrop-blur-md",
      )}
    >
      <div className="container-site flex h-16 items-center gap-4">
        <Link to="/" aria-label={L.home} className="shrink-0 rounded-lg">
          <Logo tone={light ? "dark" : "light"} />
        </Link>

        <nav aria-label={L.main} className="hidden flex-1 justify-center lg:flex">
          <ul className="flex items-center gap-0.5">
            {sections.map((id) => (
              <li key={id}>
                <SectionLink
                  id={id}
                  overHero={overHero}
                  className={cx(
                    "rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    light ? "text-white/75 hover:bg-white/10 hover:text-white" : "text-slate-600 hover:bg-fill hover:text-ink-950",
                  )}
                >
                  {labels[id]}
                </SectionLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="ms-auto flex items-center gap-2">
          <ThemeToggle
            className={cx(
              "size-10 justify-center rounded-lg",
              light ? "text-white/85 hover:bg-white/10 hover:text-white" : "text-slate-600 hover:bg-slate-100 hover:text-ink-950",
            )}
          />
          <button
            type="button"
            onClick={toggleLang}
            className={cx(
              "hidden h-10 items-center gap-1.5 rounded-lg px-3 text-sm font-medium transition-colors md:inline-flex",
              light ? "text-white/85 hover:bg-white/10 hover:text-white" : "text-slate-600 hover:bg-slate-100 hover:text-ink-950",
            )}
          >
            <Languages className="size-4" aria-hidden />
            <span lang={switchTo}>{t.otherLang}</span>
          </button>
          {loggedIn ? (
            <Link to="/" className={buttonClass(light ? "inverse" : "primary", "md", "max-sm:hidden")}>
              {L.openPanel}
            </Link>
          ) : (
            <>
              <Link to="/login" className={buttonClass(light ? "ghostInverse" : "ghost", "md", "max-md:hidden")}>
                {L.login}
              </Link>
              <Link to="/register" className={buttonClass(light ? "inverse" : "primary", "md", "max-sm:hidden")}>
                {L.start}
                <ArrowRight className="size-4 transition-transform duration-200 rtl:-scale-x-100 group-hover/btn:translate-x-0.5 rtl:group-hover/btn:-translate-x-0.5" aria-hidden />
              </Link>
            </>
          )}
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-label={L.menu}
            aria-haspopup="dialog"
            aria-expanded={menuOpen}
            className={cx(
              "-me-2 inline-flex size-11 items-center justify-center rounded-lg transition-colors lg:hidden",
              light ? "text-white hover:bg-white/10" : "text-ink-900 hover:bg-slate-100",
            )}
          >
            <Menu className="size-6" aria-hidden />
          </button>
        </div>
      </div>

      <MobileMenu open={menuOpen} onClose={() => setMenuOpen(false)} overHero={overHero} sections={sections} labels={labels} />
    </header>
  );
}

/** In-page anchor on the landing page; a router link to the landing section from anywhere else. */
function SectionLink({ id, overHero, className, children, onClick }: { id: string; overHero: boolean; className?: string; children: ReactNode; onClick?: () => void }) {
  return overHero ? (
    <a href={`#${id}`} className={className} onClick={onClick}>
      {children}
    </a>
  ) : (
    <Link to={`/#${id}`} className={className} onClick={onClick}>
      {children}
    </Link>
  );
}

function MobileMenu({
  open,
  onClose,
  overHero,
  sections,
  labels,
}: {
  open: boolean;
  onClose: () => void;
  overHero: boolean;
  sections: readonly (typeof SECTIONS)[number][];
  labels: Record<(typeof SECTIONS)[number], string>;
}) {
  const { t, lang, toggleLang } = useI18n();
  const { loggedIn } = useAuth();
  const L = t.landing.nav;
  const ref = useRef<HTMLDialogElement>(null);

  // Native modal dialog: focus trap, Esc and an inert page for free.
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      // start on the close button rather than the first link (the logo)
      d.querySelector<HTMLElement>("[data-autofocus]")?.focus();
      document.documentElement.style.overflow = "hidden";
    }
    if (!open && d.open) d.close();
  }, [open]);
  useEffect(() => () => void (document.documentElement.style.overflow = ""), []);

  // Close synchronously so an in-page anchor scrolls the unlocked page right after.
  const close = () => ref.current?.close();

  // The menu is for small screens only; widening the window closes it.
  useEffect(() => {
    if (!open) return;
    const mq = matchMedia("(min-width: 1024px)");
    const onChange = () => mq.matches && onClose();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [open, onClose]);

  return (
    <dialog
      ref={ref}
      onClose={() => {
        document.documentElement.style.overflow = "";
        onClose();
      }}
      aria-label={L.main}
      className="m-0 h-dvh max-h-none w-full max-w-none overflow-y-auto bg-surface p-0 text-ink-950 backdrop:bg-transparent lg:hidden"
    >
      {open && (
        <div className="flex min-h-full flex-col">
          <div className="container-site flex h-16 shrink-0 items-center justify-between border-b border-slate-200">
            <Link to="/" onClick={close} aria-label={L.home} className="rounded-lg">
              <Logo />
            </Link>
            <button
              type="button"
              onClick={close}
              aria-label={L.closeMenu}
              data-autofocus
              className="-me-2 inline-flex size-11 items-center justify-center rounded-lg text-ink-900 transition-colors hover:bg-slate-100"
            >
              <X className="size-6" aria-hidden />
            </button>
          </div>

          <nav aria-label={L.main} className="container-site flex-1 py-4">
            <ul>
              {sections.map((id, i) => (
                <li key={id} className="animate-pop-in border-b border-slate-100" style={{ animationDelay: `${60 + i * 45}ms` }}>
                  <SectionLink
                    id={id}
                    overHero={overHero}
                    onClick={close}
                    className="flex min-h-14 items-center justify-between text-lg font-medium transition-colors hover:text-brand-700"
                  >
                    {labels[id]}
                    <ArrowRight className="size-5 text-slate-300 rtl:-scale-x-100" aria-hidden />
                  </SectionLink>
                </li>
              ))}
            </ul>
          </nav>

          <div className="container-site animate-pop-in space-y-3 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-2" style={{ animationDelay: "240ms" }}>
            {loggedIn ? (
              <Link to="/" onClick={close} className={buttonClass("primary", "lg", "w-full")}>
                {L.openPanel}
              </Link>
            ) : (
              <>
                <Link to="/register" onClick={close} className={buttonClass("primary", "lg", "w-full")}>
                  {L.start}
                </Link>
                <Link to="/login" onClick={close} className={buttonClass("secondary", "lg", "w-full")}>
                  {L.login}
                </Link>
              </>
            )}
            <div className="flex justify-center gap-2">
              <button
                type="button"
                onClick={toggleLang}
                className="flex h-11 items-center gap-2 rounded-lg px-4 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100"
              >
                <Languages className="size-4" aria-hidden />
                <span lang={otherLang(lang)}>{t.otherLang}</span>
              </button>
              <ThemeToggle label className="h-11 rounded-lg px-4 text-sm font-medium text-slate-600 hover:bg-slate-100" />
            </div>
          </div>
        </div>
      )}
    </dialog>
  );
}
