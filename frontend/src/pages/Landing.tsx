import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { ArrowRight, BellRing, BookOpen, Check, ChevronDown, Languages, PackageSearch, ShieldCheck, SlidersHorizontal, Sparkles } from "lucide-react";
import { AskReplisto } from "../components/AskReplisto";
import HeroChat from "../components/site/HeroChat";
import SiteFooter from "../components/site/SiteFooter";
import SiteHeader from "../components/site/SiteHeader";
import { Bullets, Section, SectionHeader } from "../components/site/Section";
import { HandoffDemo, KnowledgeDemo, ProductsDemo, ToneDemo } from "../components/site/demos";
import { Reveal } from "../components/site/motion";
import { LogoMark } from "../components/Logo";
import { buttonClass, cx } from "../components/ui";
import { useI18n } from "../i18n";

/**
 * Public home page for visitors who aren't logged in. Built for phones first: what it is and
 * a live chat with our own assistant come first, then one feature at a time (tabs), three
 * setup steps, the price and the FAQ. On phones a "Start free" bar follows once the hero's
 * buttons scroll away.
 */
export default function Landing() {
  const { t } = useI18n();
  const { hash } = useLocation();
  const heroActions = useRef<HTMLDivElement>(null);
  const [showSticky, setShowSticky] = useState(false);

  useEffect(() => {
    document.title = t.landing.meta.title;
    document.querySelector('meta[name="description"]')?.setAttribute("content", t.landing.meta.description);
  }, [t]);

  // Arriving from another page at /#faq: the router doesn't scroll to the anchor by itself.
  useEffect(() => {
    if (hash) document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView();
  }, [hash]);

  // The sticky "Start free" bar appears once the hero's own buttons are out of view.
  useEffect(() => {
    const el = heroActions.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setShowSticky(!entry.isIntersecting && entry.boundingClientRect.top < 0));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="bg-surface text-ink-950">
      <a
        href="#main"
        className="sr-only z-50 rounded-lg bg-surface px-4 py-2 font-semibold text-ink-950 shadow-lift focus:not-sr-only focus:fixed focus:start-4 focus:top-4"
      >
        {t.landing.nav.skip}
      </a>
      <SiteHeader />
      <main id="main">
        <Hero actionsRef={heroActions} />
        <Try />
        <Features />
        <Steps />
        <Pricing />
        <Faq />
        <FinalCta />
      </main>
      <SiteFooter onLanding />
      <StickyCta show={showSticky} />
    </div>
  );
}

function Arrow() {
  return (
    <ArrowRight
      aria-hidden
      className="size-4 transition-transform duration-200 rtl:-scale-x-100 group-hover/btn:translate-x-0.5 rtl:group-hover/btn:-translate-x-0.5"
    />
  );
}

function Hero({ actionsRef }: { actionsRef: React.RefObject<HTMLDivElement | null> }) {
  const { t } = useI18n();
  const h = t.landing.home;
  return (
    <section aria-labelledby="hero-title" className="relative overflow-hidden">
      {/* soft teal and coral light behind the headline */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute -top-40 start-1/2 size-[42rem] -translate-x-1/2 rounded-full bg-brand-200/45 blur-3xl rtl:translate-x-1/2 dark:bg-brand-300/25" />
        <div className="absolute -top-10 end-[-10rem] size-[22rem] rounded-full bg-accent-200/60 blur-3xl dark:bg-accent-500/10" />
      </div>
      <div className="container-site relative grid grid-cols-1 items-center gap-x-16 gap-y-12 pb-12 pt-8 sm:pb-16 sm:pt-12 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:pb-24 lg:pt-16">
        <div className="max-w-2xl">
          <p className="animate-pop-in inline-flex items-center gap-2 rounded-full bg-surface/80 px-3 py-1.5 text-[13px] font-semibold text-brand-800 shadow-soft ring-1 ring-brand-100 backdrop-blur">
            <Sparkles aria-hidden className="size-3.5 text-accent-500" />
            {h.eyebrow}
          </p>
          <h1 id="hero-title" className="t-display animate-pop-in mt-5 text-balance text-ink-950 [animation-delay:80ms]">
            {h.titleBefore}
            <span className="relative inline-block whitespace-nowrap text-brand-600">
              {h.titleMark}
              <svg aria-hidden viewBox="0 0 200 14" preserveAspectRatio="none" className="absolute inset-x-0 -bottom-1 h-[0.2em] w-full text-accent-400 rtl:-scale-x-100">
                <path d="M3 10 C 48 3, 118 2, 197 8" pathLength="1" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" className="draw-in" />
              </svg>
            </span>
            {h.titleAfter}
          </h1>
          <p className="t-lead animate-pop-in mt-5 max-w-xl text-pretty text-slate-600 [animation-delay:160ms]">{h.lead}</p>
          <div ref={actionsRef} className="animate-pop-in mt-7 flex flex-col gap-3 [animation-delay:240ms] sm:flex-row">
            <Link to="/register" className={buttonClass("primary", "lg", "group/btn")}>
              {h.primary}
              <Arrow />
            </Link>
            <a href="#try" className={buttonClass("secondary", "lg")}>
              {h.secondary}
            </a>
          </div>
          <ul className="animate-pop-in mt-6 flex flex-wrap gap-x-5 gap-y-2 [animation-delay:320ms]">
            {h.perks.map((perk) => (
              <li key={perk} className="flex items-center gap-1.5 text-sm font-medium text-slate-600">
                <Check aria-hidden className="size-4 text-brand-600" strokeWidth={3} />
                {perk}
              </li>
            ))}
          </ul>
          <p className="animate-pop-in mt-4 flex items-center gap-2 text-sm text-slate-500 [animation-delay:380ms]">
            <Languages aria-hidden className="size-4 shrink-0 text-brand-600" />
            {h.languages}
          </p>
        </div>
        {/* phones get the live chat right below instead of a second demo */}
        <div className="animate-pop-in hidden [animation-delay:200ms] lg:block">
          <HeroChat />
        </div>
      </div>
    </section>
  );
}

/** The real thing: our own assistant, answering questions about Replisto. */
function Try() {
  const { t } = useI18n();
  const h = t.landing.home;
  return (
    <Section id="try" tone="tint" compact>
      <div className="grid grid-cols-1 items-center gap-x-16 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div>
          <SectionHeader id="try" eyebrow={h.tryEyebrow} title={h.tryTitle} lead={h.tryLead} align="start" />
          <ul className="mt-6 hidden space-y-3 lg:block">
            {h.tryPoints.map((point) => (
              <li key={point} className="flex items-start gap-3 text-[15px] leading-7 text-slate-700">
                <Check className="mt-1 size-5 shrink-0 text-brand-600" aria-hidden />
                {point}
              </li>
            ))}
          </ul>
        </div>
        <Reveal delay={80}>
          <AskReplisto />
        </Reveal>
      </div>
    </Section>
  );
}

/** One feature at a time: tabs on top (swipeable on phones), the copy and its demo below. */
function Features() {
  const { t } = useI18n();
  const F = t.landing.features;
  const h = t.landing.home;
  const items: { icon: ReactNode; copy: { title: string; body: string; bullets: readonly string[] }; demo: ReactNode }[] = [
    { icon: <BookOpen />, copy: F.knowledge, demo: <KnowledgeDemo /> },
    { icon: <PackageSearch />, copy: F.products, demo: <ProductsDemo /> },
    { icon: <BellRing />, copy: F.handoff, demo: <HandoffDemo /> },
    { icon: <SlidersHorizontal />, copy: F.control, demo: <ToneDemo /> },
  ];
  const [active, setActive] = useState(0);
  const item = items[active];
  return (
    <Section id="features">
      <SectionHeader id="features" eyebrow={h.featuresEyebrow} title={h.featuresTitle} />
      <div role="tablist" aria-label={h.featuresTitle} className="no-scrollbar -mx-4 mt-8 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:justify-center sm:px-0">
        {items.map((it, i) => (
          <button
            key={h.tabs[i]}
            type="button"
            role="tab"
            id={`feature-tab-${i}`}
            aria-selected={active === i}
            aria-controls="feature-panel"
            onClick={() => setActive(i)}
            className={cx(
              "flex shrink-0 items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold ring-1 transition-colors [&>svg]:size-4",
              active === i ? "bg-ink-900 text-white ring-ink-900 dark:bg-brand-600 dark:ring-brand-600" : "bg-surface text-slate-600 ring-slate-200 hover:text-ink-950",
            )}
          >
            {it.icon}
            {h.tabs[i]}
          </button>
        ))}
      </div>
      <div
        id="feature-panel"
        role="tabpanel"
        aria-labelledby={`feature-tab-${active}`}
        key={active}
        className="animate-pop-in mt-8 grid grid-cols-1 items-center gap-x-14 gap-y-8 lg:mt-12 lg:grid-cols-2"
      >
        <div className="max-w-xl">
          <h3 className="t-h3 text-ink-950">{item.copy.title}</h3>
          <p className="mt-3 text-[16px] leading-7 text-slate-600">{item.copy.body}</p>
          <Bullets items={item.copy.bullets} className="mt-5" />
        </div>
        <div className="mx-auto w-full max-w-lg">{item.demo}</div>
      </div>
    </Section>
  );
}

/** Three steps: swipeable cards on phones, a row on larger screens. */
function Steps() {
  const { t, f } = useI18n();
  const h = t.landing.home;
  return (
    <Section id="how" tone="tint" compact>
      <SectionHeader id="how" eyebrow={h.stepsEyebrow} title={h.stepsTitle} />
      <ol className="no-scrollbar -mx-4 mt-8 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-2 sm:mx-0 sm:grid sm:grid-cols-3 sm:gap-5 sm:overflow-visible sm:px-0">
        {h.steps.map((step, i) => (
          <li key={step.title} className="w-[78%] shrink-0 snap-center sm:w-auto">
            <Reveal delay={i * 90} className="h-full rounded-2xl bg-surface p-5 shadow-soft ring-1 ring-line sm:p-6">
              <span className="num flex size-10 items-center justify-center rounded-xl bg-brand-600 text-base font-extrabold text-white">{f.num(i + 1)}</span>
              <h3 className="mt-4 text-lg font-bold text-ink-950">{step.title}</h3>
              <p className="mt-1.5 text-[15px] leading-7 text-slate-600">{step.body}</p>
            </Reveal>
          </li>
        ))}
      </ol>
    </Section>
  );
}

function Pricing() {
  const { t } = useI18n();
  const h = t.landing.home;
  return (
    <Section id="pricing" compact>
      <div className="mx-auto max-w-3xl">
        <Reveal className="overflow-hidden rounded-3xl bg-night-900 text-white shadow-float">
          <div className="grid grid-cols-1 gap-8 p-6 sm:p-9 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
            <div>
              <p className="text-sm font-bold text-accent-300">{h.pricingEyebrow}</p>
              <h2 id="pricing-title" className="t-h2 mt-2 text-balance">
                {h.pricingTitle}
              </h2>
              <p className="mt-3 text-[15px] leading-7 text-white/70">{h.pricingLead}</p>
              <ul className="mt-6 space-y-2.5">
                {h.pricingPoints.map((point) => (
                  <li key={point} className="flex items-start gap-2.5 text-[15px] text-white/90">
                    <Check aria-hidden className="mt-0.5 size-5 shrink-0 text-accent-300" strokeWidth={2.5} />
                    {point}
                  </li>
                ))}
              </ul>
            </div>
            <div className="flex flex-col items-start gap-4 rounded-2xl bg-white/[0.06] p-6 ring-1 ring-white/10 md:items-center md:text-center">
              <div>
                <span className="num text-5xl font-extrabold tracking-tight">{h.pricingPrice}</span>
                <span className="ms-2 text-sm text-white/60">{h.pricingUnit}</span>
              </div>
              <Link to="/register" className={buttonClass("inverse", "lg", "group/btn w-full")}>
                {h.pricingCta}
                <Arrow />
              </Link>
            </div>
          </div>
          <ul className="flex flex-wrap gap-x-5 gap-y-2 border-t border-white/10 px-6 py-4 text-[13px] text-white/60 sm:px-9">
            {h.trust.map((item) => (
              <li key={item} className="flex items-center gap-1.5">
                <ShieldCheck aria-hidden className="size-4 text-brand-300" />
                {item}
              </li>
            ))}
          </ul>
        </Reveal>
      </div>
    </Section>
  );
}

function Faq() {
  const { t } = useI18n();
  const Q = t.landing.faq;
  return (
    <Section id="faq" tone="tint" compact>
      <div className="mx-auto max-w-3xl">
        <SectionHeader id="faq" eyebrow={Q.eyebrow} title={Q.title} />
        <Reveal className="mt-8">
          <div className="divide-y divide-slate-200 overflow-hidden rounded-2xl bg-surface ring-1 ring-line">
            {Q.items.map((item) => (
              <details key={item.q} name="faq" className="group">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 text-start text-[16px] font-semibold text-ink-950 transition-colors hover:text-brand-700 [&::-webkit-details-marker]:hidden">
                  {item.q}
                  <span
                    aria-hidden
                    className="flex size-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500 transition-[transform,background-color,color] duration-300 group-open:rotate-180 group-open:bg-brand-600 group-open:text-white"
                  >
                    <ChevronDown className="size-4" />
                  </span>
                </summary>
                <p className="animate-pop-in px-5 pb-5 pe-12 text-[15px] leading-7 text-slate-600">{item.a}</p>
              </details>
            ))}
          </div>
        </Reveal>
      </div>
    </Section>
  );
}

function FinalCta() {
  const { t } = useI18n();
  const C = t.landing.cta;
  return (
    <section aria-labelledby="cta-title" className="relative overflow-hidden bg-brand-600 text-white">
      <div aria-hidden className="dot-grid absolute inset-0 [mask-image:radial-gradient(ellipse_60%_80%_at_50%_100%,black,transparent)]" />
      <Reveal className="container-site relative flex flex-col items-center py-[clamp(3.5rem,8vw,6rem)] text-center">
        <LogoMark px={56} className="shadow-float ring-2 ring-white/25" />
        <h2 id="cta-title" className="t-h2 mt-6 max-w-2xl text-balance">
          {C.title}
        </h2>
        <p className="mt-3 max-w-xl text-pretty text-[16px] leading-7 text-white/80">{C.lead}</p>
        <div className="mt-8 flex w-full flex-col justify-center gap-3 sm:w-auto sm:flex-row">
          <Link to="/register" className={buttonClass("inverse", "lg", "group/btn")}>
            {C.primary}
            <Arrow />
          </Link>
          <Link to="/login" className={buttonClass("outlineInverse", "lg")}>
            {C.secondary}
          </Link>
        </div>
      </Reveal>
    </section>
  );
}

/** Phones: a "Start free" bar at the bottom once the hero's buttons have scrolled away. */
function StickyCta({ show }: { show: boolean }) {
  const { t } = useI18n();
  return (
    <div
      aria-hidden={!show}
      className={cx(
        "fixed inset-x-0 bottom-0 z-30 border-t border-slate-200/80 bg-surface/95 px-4 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-3 backdrop-blur-md transition-transform duration-300 lg:hidden",
        show ? "translate-y-0" : "pointer-events-none translate-y-full",
      )}
    >
      <Link to="/register" tabIndex={show ? 0 : -1} className={buttonClass("primary", "lg", "group/btn w-full")}>
        {t.landing.home.stickyCta}
        <Arrow />
      </Link>
    </div>
  );
}
