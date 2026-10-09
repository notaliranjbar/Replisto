import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import {
  ArrowRight,
  BarChart3,
  BellRing,
  BookOpen,
  CalendarClock,
  Check,
  Inbox,
  MessageCircleMore,
  PackageSearch,
  Plus,
  Search,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import { AskReplisto } from "../components/AskReplisto";
import SiteFooter from "../components/site/SiteFooter";
import SiteHeader from "../components/site/SiteHeader";
import { Bullets, Section, SectionHeader } from "../components/site/Section";
import { CommentsDemo, HandoffDemo, InsightsDemo, KnowledgeDemo, ProductsDemo, StoriesDemo, ToneDemo } from "../components/site/demos";
import { Reveal } from "../components/site/motion";
import { LogoMark } from "../components/Logo";
import { buttonClass, cx } from "../components/ui";
import { useI18n } from "../i18n";

/**
 * Public home page for visitors who aren't logged in. A centred headline over a picture of the
 * product (the inbox), a strip of plain numbers, then a live chat with our own assistant, the
 * features, three setup steps, the price and the FAQ. On phones a "Start free" bar follows once
 * the hero's buttons scroll away.
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
      <Announcement />
      <SiteHeader />
      <main id="main">
        <Hero actionsRef={heroActions} />
        <Metrics />
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

/** A slim navy bar above the header with the latest news. */
function Announcement() {
  const { t } = useI18n();
  const h = t.landing.home;
  return (
    <div className="bg-night-950 text-white">
      <div className="container-site flex min-h-10 items-center justify-center gap-x-3 py-2 text-center text-[13px]">
        <span className="text-white/80">{h.announce}</span>
        <a href="#try" className="inline-flex shrink-0 items-center gap-1 font-medium text-[#93b1fb] hover:text-white">
          {h.announceLink}
          <ArrowRight aria-hidden className="size-3.5 rtl:-scale-x-100" />
        </a>
      </div>
    </div>
  );
}

function Hero({ actionsRef }: { actionsRef: React.RefObject<HTMLDivElement | null> }) {
  const { t } = useI18n();
  const h = t.landing.home;
  return (
    <section aria-labelledby="hero-title" className="relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(55%_45%_at_50%_0%,rgb(37_72_224/0.09),transparent)]" />
      <div aria-hidden className="line-grid pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,black,transparent)]" />
      <div className="container-site relative pb-12 pt-12 text-center sm:pt-16 lg:pt-20">
        <p className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-surface px-3 py-1 text-[13px] font-medium text-slate-600 shadow-soft">
          <span aria-hidden className="size-1.5 rounded-full bg-brand-600" />
          {h.eyebrow}
        </p>
        <h1 id="hero-title" className="t-display mx-auto mt-5 max-w-4xl text-ink-950 max-sm:text-balance">
          {h.titleBefore}
          <br />
          <span className="t-accent">{h.titleMark}</span>
          {h.titleAfter}
        </h1>
        <p className="t-lead mx-auto mt-5 max-w-2xl text-pretty text-slate-600">{h.lead}</p>
        <div ref={actionsRef} className="mx-auto mt-8 flex max-w-sm flex-col justify-center gap-3 sm:max-w-none sm:flex-row">
          <Link to="/register" className={buttonClass("primary", "lg", "group/btn")}>
            {h.primary}
            <Arrow />
          </Link>
          <a href="#try" className={buttonClass("secondary", "lg")}>
            {h.secondary}
          </a>
        </div>
        <ul className="mt-6 flex flex-wrap justify-center gap-x-5 gap-y-2">
          {h.perks.map((perk) => (
            <li key={perk} className="flex items-center gap-1.5 text-sm text-slate-600">
              <Check aria-hidden className="size-4 text-emerald-600" strokeWidth={2.5} />
              {perk}
            </li>
          ))}
        </ul>
        {/* phones skip the picture: the live chat follows right below */}
        <div className="mx-auto mt-14 hidden max-w-5xl sm:block">
          <InboxMock />
        </div>
      </div>
    </section>
  );
}

/** A still picture of the panel's inbox: the thread list and one answered conversation. */
function InboxMock() {
  const { t } = useI18n();
  const m = t.landing.home.mock;
  const c = t.landing.chat;
  return (
    <div aria-hidden className="overflow-hidden rounded-xl border border-slate-200 bg-surface text-start shadow-float">
      <div className="flex h-11 items-center gap-2.5 border-b border-slate-200 bg-slate-50 px-4">
        <LogoMark px={20} />
        <span className="text-[13px] font-semibold text-ink-900">{m.title}</span>
        <span className="ms-auto flex h-7 w-48 items-center gap-2 rounded-md border border-slate-200 bg-surface px-2.5 text-xs text-slate-400 max-md:hidden">
          <Search className="size-3.5" />
        </span>
      </div>
      <div className="grid h-[23rem] grid-cols-[15rem_minmax(0,1fr)] max-md:grid-cols-1">
        <div className="border-e border-slate-200 max-md:hidden">
          <div className="flex gap-4 border-b border-slate-200 px-4 text-xs font-medium">
            <span className="-mb-px border-b-2 border-brand-600 py-2.5 text-ink-950">{m.all}</span>
            <span className="py-2.5 text-slate-500">{m.waiting}</span>
          </div>
          <ul>
            {m.threads.map((th, i) => (
              <li key={th.name} className={cx("flex gap-3 border-b border-slate-100 px-4 py-3", i === 0 && "bg-brand-50")}>
                <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-slate-200 text-xs font-semibold uppercase text-slate-600">{th.name[0]}</span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="ltr truncate text-[13px] font-semibold text-ink-900">{th.name}</span>
                    <span className="ms-auto shrink-0 text-[11px] text-slate-400">{th.time}</span>
                  </span>
                  <span className="mt-0.5 flex items-center gap-1.5">
                    <span className="truncate text-xs text-slate-500">{th.text}</span>
                    {"waiting" in th && th.waiting && <span className="size-1.5 shrink-0 rounded-full bg-red-500" />}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex min-w-0 flex-col">
          <div className="flex h-12 items-center gap-2.5 border-b border-slate-200 px-5">
            <span className="ltr text-sm font-semibold text-ink-900">{m.threads[0].name}</span>
            <span className="ms-auto inline-flex items-center gap-1.5 rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200">
              <span className="size-1.5 rounded-full bg-emerald-500" />
              {c.botOn}
            </span>
          </div>
          <div className="flex-1 space-y-3 overflow-hidden bg-canvas/60 px-5 py-4 text-[13px] leading-6">
            <p className="w-fit max-w-[75%] rounded-lg rounded-ss-sm border border-slate-200 bg-surface px-3 py-2 text-ink-900">{c.m1}</p>
            <div className="ms-auto w-fit max-w-[75%]">
              <p className="rounded-lg rounded-se-sm bg-brand-600 px-3 py-2 text-white">{c.m2}</p>
              <p className="mt-1 flex items-center justify-end gap-1 text-[11px] text-slate-500">
                <Check className="size-3 text-brand-600" strokeWidth={3} />
                {m.auto} · {c.lookup}
              </p>
            </div>
            <p className="w-fit max-w-[75%] rounded-lg rounded-ss-sm border border-slate-200 bg-surface px-3 py-2 text-ink-900">{c.m3}</p>
            <div className="ms-auto w-fit max-w-[75%]">
              <p className="rounded-lg rounded-se-sm bg-brand-600 px-3 py-2 text-white">{c.m4}</p>
              <p className="mt-1 flex items-center justify-end gap-1 text-[11px] text-slate-500">
                <Check className="size-3 text-brand-600" strokeWidth={3} />
                {m.auto}
              </p>
            </div>
          </div>
          <div className="flex h-12 items-center border-t border-slate-200 px-5 text-xs text-slate-400">{m.reply}</div>
        </div>
      </div>
    </div>
  );
}

/** Four plain numbers in a ruled strip. */
function Metrics() {
  const { t } = useI18n();
  return (
    <section aria-label={t.landing.home.featuresEyebrow} className="bg-night-950 text-white">
      <dl className="container-site grid grid-cols-2 md:grid-cols-4">
        {t.landing.home.metrics.map((m, i) => (
          <div
            key={m.label}
            className={cx(
              "border-white/10 px-2 py-6 text-center sm:py-8",
              i % 2 === 0 && "border-e",
              i < 2 && "max-md:border-b",
              i === 1 && "md:border-e",
            )}
          >
            <dt className="sr-only">{m.label}</dt>
            <dd dir="auto" className="num text-2xl font-semibold tracking-tight text-white sm:text-3xl">{m.value}</dd>
            <dd className="mt-1 text-[13px] text-white/60 sm:text-sm">{m.label}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** The real thing: our own assistant, answering questions about Replisto. */
function Try() {
  const { t } = useI18n();
  const h = t.landing.home;
  return (
    <Section id="try" compact>
      <div className="grid grid-cols-1 items-center gap-x-16 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div>
          <SectionHeader id="try" eyebrow={h.tryEyebrow} title={h.tryTitle} lead={h.tryLead} align="start" />
          <ul className="mt-6 hidden space-y-3 lg:block">
            {h.tryPoints.map((point) => (
              <li key={point} className="flex items-start gap-3 text-[15px] leading-7 text-slate-700">
                <Check className="mt-1 size-5 shrink-0 text-emerald-600" aria-hidden />
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

/**
 * One feature at a time. Desktop: a vertical list on the start side (the open one shows its
 * summary) and the demo beside it. Phones: underline tabs that scroll sideways, then the copy.
 */
function Features() {
  const { t } = useI18n();
  const F = t.landing.features;
  const h = t.landing.home;
  const items: { icon: ReactNode; copy: { title: string; body: string; bullets: readonly string[] }; demo: ReactNode }[] = [
    { icon: <BookOpen />, copy: F.knowledge, demo: <KnowledgeDemo /> },
    { icon: <PackageSearch />, copy: F.products, demo: <ProductsDemo /> },
    { icon: <MessageCircleMore />, copy: F.comments, demo: <CommentsDemo /> },
    { icon: <CalendarClock />, copy: F.stories, demo: <StoriesDemo /> },
    { icon: <BarChart3 />, copy: F.insights, demo: <InsightsDemo /> },
    { icon: <BellRing />, copy: F.handoff, demo: <HandoffDemo /> },
    { icon: <SlidersHorizontal />, copy: F.control, demo: <ToneDemo /> },
  ];
  const [active, setActive] = useState(0);
  const item = items[active];
  return (
    <Section id="features" tone="tint">
      <SectionHeader id="features" eyebrow={h.featuresEyebrow} title={h.featuresTitle} align="start" />
      <div className="mt-8 grid grid-cols-1 gap-x-12 gap-y-6 lg:mt-12 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <div
          role="tablist"
          aria-label={h.featuresTitle}
          aria-orientation="vertical"
          className="no-scrollbar -mx-4 flex gap-5 overflow-x-auto border-b border-slate-200 px-4 sm:mx-0 sm:px-0 lg:flex-col lg:gap-2 lg:overflow-visible lg:border-0"
        >
          {items.map((it, i) => {
            const on = active === i;
            return (
              <button
                key={h.tabs[i]}
                type="button"
                role="tab"
                id={`feature-tab-${i}`}
                aria-selected={on}
                aria-controls="feature-panel"
                onClick={() => setActive(i)}
                className={cx(
                  "-mb-px flex shrink-0 items-center gap-2 border-b-2 py-3 text-sm font-medium transition-colors [&>svg]:size-4",
                  "lg:mb-0 lg:gap-3 lg:rounded-lg lg:border lg:px-3 lg:py-2.5 lg:text-start",
                  on
                    ? "border-brand-600 text-ink-950 lg:border-slate-200 lg:bg-surface lg:shadow-soft"
                    : "border-transparent text-slate-500 hover:text-ink-900 lg:hover:bg-surface/60",
                )}
              >
                <span className={cx("flex shrink-0 items-center [&>svg]:size-4 lg:size-8 lg:justify-center lg:rounded-md lg:border lg:border-slate-200 lg:bg-surface", on ? "text-brand-600" : "text-slate-400")}>
                  {it.icon}
                </span>
                <span className="min-w-0 lg:self-center lg:text-[15px]">{h.tabs[i]}</span>
              </button>
            );
          })}
        </div>
        <div id="feature-panel" role="tabpanel" aria-labelledby={`feature-tab-${active}`} key={active} className="animate-fade-in grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] xl:gap-10">
          <div>
            <h3 className="t-h3 text-ink-950">{item.copy.title}</h3>
            <p className="mt-2 text-[15px] leading-7 text-slate-600">{item.copy.body}</p>
            <Bullets items={item.copy.bullets} className="mt-5" />
          </div>
          <Reveal className="w-full">{item.demo}</Reveal>
        </div>
      </div>
    </Section>
  );
}

/** Three steps on a line: down the page on phones, across it on larger screens. */
function Steps() {
  const { t, f } = useI18n();
  const h = t.landing.home;
  return (
    <Section id="how" compact>
      <SectionHeader id="how" eyebrow={h.stepsEyebrow} title={h.stepsTitle} align="start" />
      <ol className="mt-10 grid grid-cols-1 gap-8 sm:grid-cols-3 sm:gap-6">
        {h.steps.map((step, i) => (
          <li key={step.title} className="relative ps-12 sm:ps-0 sm:pt-14">
            {/* connector to the next step */}
            {i < h.steps.length - 1 && (
              <span
                aria-hidden
                className="absolute start-[0.9375rem] top-9 -bottom-8 w-px bg-slate-200 sm:start-11 sm:-end-6 sm:top-4 sm:bottom-auto sm:h-px sm:w-auto"
              />
            )}
            <span className="num absolute start-0 top-0 flex size-8 items-center justify-center rounded-full border border-brand-600 bg-surface text-sm font-semibold text-brand-700">
              {f.num(i + 1)}
            </span>
            <h3 className="text-[17px] font-semibold tracking-tight text-ink-950">{step.title}</h3>
            <p className="mt-1.5 text-[15px] leading-7 text-slate-600">{step.body}</p>
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
    <Section id="pricing" tone="tint" compact>
      <Reveal className="mx-auto max-w-4xl overflow-hidden rounded-xl border border-slate-200 bg-surface shadow-lift">
        <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_17rem]">
          <div className="p-6 sm:p-8">
            <p className="text-[13px] font-semibold uppercase tracking-wider text-brand-600">{h.pricingEyebrow}</p>
            <h2 id="pricing-title" className="t-h2 mt-2 text-balance text-ink-950">
              {h.pricingTitle}
            </h2>
            <p className="mt-3 text-[15px] leading-7 text-slate-600">{h.pricingLead}</p>
            <ul className="mt-6 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {h.pricingPoints.map((point) => (
                <li key={point} className="flex items-start gap-2.5 text-sm leading-6 text-slate-700">
                  <Check aria-hidden className="mt-0.5 size-4 shrink-0 text-emerald-600" strokeWidth={2.5} />
                  {point}
                </li>
              ))}
            </ul>
          </div>
          <div className="flex flex-col justify-center gap-5 border-t border-slate-200 bg-slate-50 p-6 sm:p-8 md:border-s md:border-t-0">
            <div>
              <span dir="auto" className="num text-4xl font-semibold tracking-tight text-ink-950">{h.pricingPrice}</span>
              <span className="ms-2 text-sm text-slate-500">{h.pricingUnit}</span>
            </div>
            <Link to="/register" className={buttonClass("primary", "lg", "group/btn w-full")}>
              {h.pricingCta}
              <Arrow />
            </Link>
          </div>
        </div>
        <ul className="flex flex-wrap gap-x-5 gap-y-2 border-t border-slate-200 px-6 py-4 text-[13px] text-slate-500 sm:px-8">
          {h.trust.map((item) => (
            <li key={item} className="flex items-center gap-1.5">
              <ShieldCheck aria-hidden className="size-4 text-slate-400" />
              {item}
            </li>
          ))}
        </ul>
      </Reveal>
    </Section>
  );
}

function Faq() {
  const { t } = useI18n();
  const Q = t.landing.faq;
  return (
    <Section id="faq" compact>
      <div className="grid grid-cols-1 gap-x-16 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.7fr)]">
        <SectionHeader id="faq" eyebrow={Q.eyebrow} title={Q.title} align="start" />
        <div className="divide-y divide-slate-200 border-y border-slate-200">
          {Q.items.map((item) => (
            <details key={item.q} name="faq" className="group">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-4 text-start text-[15px] font-medium text-ink-950 transition-colors hover:text-brand-700 [&::-webkit-details-marker]:hidden">
                {item.q}
                <Plus aria-hidden className="size-4 shrink-0 text-slate-400 transition-transform duration-200 group-open:rotate-45" />
              </summary>
              <p className="animate-fade-in pb-5 pe-8 text-[15px] leading-7 text-slate-600">{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </Section>
  );
}

function FinalCta() {
  const { t } = useI18n();
  const C = t.landing.cta;
  return (
    <section aria-labelledby="cta-title" className="relative overflow-hidden bg-night-950 text-white">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,rgb(255_255_255/0.05)_1px,transparent_1px),linear-gradient(to_bottom,rgb(255_255_255/0.05)_1px,transparent_1px)] bg-[size:48px_48px] [mask-image:radial-gradient(ellipse_60%_100%_at_100%_50%,black,transparent)] rtl:[mask-image:radial-gradient(ellipse_60%_100%_at_0%_50%,black,transparent)]"
      />
      <div className="container-site relative flex flex-col gap-8 py-[clamp(3.5rem,7vw,5.5rem)] md:flex-row md:items-center md:justify-between">
        <div className="max-w-xl">
          <h2 id="cta-title" className="t-h2 text-balance">
            {C.title}
          </h2>
          <p className="mt-3 text-pretty text-[16px] leading-7 text-white/70">{C.lead}</p>
        </div>
        <div className="flex shrink-0 flex-col gap-3 sm:flex-row">
          <Link to="/register" className={buttonClass("primary", "lg", "group/btn")}>
            {C.primary}
            <Arrow />
          </Link>
          <Link to="/login" className={buttonClass("outlineInverse", "lg")}>
            <Inbox aria-hidden className="size-4" />
            {C.secondary}
          </Link>
        </div>
      </div>
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
        "fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-surface/95 px-4 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-3 backdrop-blur-md transition-transform duration-300 lg:hidden",
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
