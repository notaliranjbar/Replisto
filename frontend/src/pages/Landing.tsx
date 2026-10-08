import { useEffect, useRef, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import {
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  Clock,
  EyeOff,
  Hand,
  Inbox,
  KeyRound,
  PackageSearch,
  ShieldCheck,
  SlidersHorizontal,
  Trash,
  UserRound,
  BellRing,
  BookOpenCheck,
  ShoppingBag,
  Headset,
  Compass,
  ClipboardList,
  ListChecks,
} from "lucide-react";
import { CHANNELS, ChannelMark } from "../components/site/channels";
import HeroChat from "../components/site/HeroChat";
import SiteFooter from "../components/site/SiteFooter";
import SiteHeader from "../components/site/SiteHeader";
import { Bullets, Section, SectionHeader } from "../components/site/Section";
import { HandoffDemo, KnowledgeDemo, ProductsDemo, ToneDemo } from "../components/site/demos";
import { Reveal, useInView } from "../components/site/motion";
import { LogoMark } from "../components/Logo";
import { buttonClass, cx } from "../components/ui";
import { useI18n } from "../i18n";

/** Public home page for visitors who aren't logged in. */
export default function Landing() {
  const { t } = useI18n();
  const { hash } = useLocation();

  useEffect(() => {
    document.title = t.landing.meta.title;
    document.querySelector('meta[name="description"]')?.setAttribute("content", t.landing.meta.description);
  }, [t]);

  // Arriving from another page at /#faq: the router doesn't scroll to the anchor by itself.
  useEffect(() => {
    if (hash) document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView();
  }, [hash]);

  return (
    <div className="bg-surface text-ink-950">
      <a
        href="#main"
        className="sr-only z-50 rounded-lg bg-surface px-4 py-2 font-semibold text-ink-950 shadow-lift focus:not-sr-only focus:fixed focus:start-4 focus:top-4"
      >
        {t.landing.nav.skip}
      </a>
      <SiteHeader overHero />
      <main id="main">
        <Hero />
        <Roles />
        <Channels />
        <Problem />
        <Features />
        <How />
        <Trust />
        <Faq />
        <FinalCta />
      </main>
      <SiteFooter onLanding />
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

function Hero() {
  const { t } = useI18n();
  const h = t.landing.hero;
  return (
    <section aria-labelledby="hero-title" className="relative overflow-hidden bg-brand-600 text-white">
      <div aria-hidden className="dot-grid absolute inset-0 [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,black,transparent)]" />
      <div className="container-site relative grid grid-cols-1 items-center gap-x-16 gap-y-16 pb-20 pt-10 sm:pt-14 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:pb-28 lg:pt-16">
        <div className="max-w-2xl">
          <p className="animate-pop-in inline-flex items-center gap-2 rounded-full bg-white/10 px-3.5 py-1.5 text-sm font-medium text-white/90 ring-1 ring-white/20">
            <span aria-hidden className="size-1.5 rounded-full bg-accent-400" />
            {h.eyebrow}
          </p>
          <h1 id="hero-title" className="t-display animate-pop-in mt-6 text-balance [animation-delay:80ms]">
            {h.titleBefore}
            <span className="relative inline-block whitespace-nowrap text-accent-300">
              {h.titleMark}
              <svg aria-hidden viewBox="0 0 200 14" preserveAspectRatio="none" className="absolute inset-x-0 -bottom-1.5 h-[0.22em] w-full rtl:-scale-x-100">
                <path d="M3 10 C 48 3, 118 2, 197 8" pathLength="1" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" className="draw-in" />
              </svg>
            </span>
            {h.titleAfter}
          </h1>
          <p className="t-lead animate-pop-in mt-6 max-w-xl text-pretty text-white/80 [animation-delay:160ms]">{h.lead}</p>
          <div className="animate-pop-in mt-9 flex flex-col gap-3 [animation-delay:240ms] sm:flex-row sm:flex-wrap">
            <Link to="/register" className={buttonClass("inverse", "lg")}>
              {h.primary}
              <Arrow />
            </Link>
            <a href="#roles" className={buttonClass("outlineInverse", "lg")}>
              {h.secondary}
            </a>
          </div>
          {/* what it does, then where it works: the first screen answers both */}
          <div className="animate-pop-in mt-9 space-y-4 [animation-delay:320ms]">
            <ul aria-label={h.rolesLabel} className="flex flex-wrap gap-2">
              {h.roles.map((role) => (
                <li key={role} className="rounded-full bg-white/10 px-3.5 py-1.5 text-sm font-semibold text-white ring-1 ring-white/20">
                  {role}
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-white/75">
              <span>{h.channelsLabel}</span>
              <ul className="flex gap-2">
                {CHANNELS.map(({ key }) => (
                  <li
                    key={key}
                    title={t.landing.channels.names[key]}
                    className="flex size-9 items-center justify-center rounded-xl bg-white/10 text-white ring-1 ring-white/15"
                  >
                    <ChannelMark channel={key} className="size-[18px]" />
                    <span className="sr-only">{t.landing.channels.names[key]}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
        <div className="animate-pop-in [animation-delay:200ms]">
          <HeroChat />
        </div>
      </div>
    </section>
  );
}

/** The jobs Replisto does for a business: five equal roles, one card each. */
function Roles() {
  const { t } = useI18n();
  const R = t.landing.roles;
  const icons = [<ShoppingBag key="s" />, <Headset key="h" />, <Compass key="c" />, <ClipboardList key="a" />, <ListChecks key="f" />];
  return (
    <Section id="roles">
      <SectionHeader id="roles" eyebrow={R.eyebrow} title={R.title} lead={R.lead} />
      <ul className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:mt-14 lg:grid-cols-5">
        {R.items.map((item, i) => (
          <li key={item.title} className="sm:last:col-span-2 lg:last:col-span-1">
            <Reveal
              delay={i * 70}
              className="h-full rounded-2xl bg-surface p-6 shadow-soft ring-1 ring-line transition-[box-shadow,transform] duration-200 hover:-translate-y-0.5 hover:shadow-lift"
            >
              <span aria-hidden className="flex size-11 items-center justify-center rounded-xl bg-brand-50 text-brand-700 [&>svg]:size-5">
                {icons[i]}
              </span>
              <h3 className="mt-5 text-lg font-bold text-ink-950">{item.title}</h3>
              <p className="mt-2 text-[15px] leading-7 text-slate-600">{item.body}</p>
            </Reveal>
          </li>
        ))}
      </ul>
    </Section>
  );
}

/**
 * The messaging channels Replisto works on, as identical tiles. Channels that aren't connected in
 * the product yet say "coming soon" instead of offering a dead button.
 */
function Channels() {
  const { t } = useI18n();
  const C = t.landing.channels;
  return (
    <Section id="channels" tone="tint" compact>
      <SectionHeader id="channels" eyebrow={C.eyebrow} title={C.title} lead={C.lead} />
      <ul className="mx-auto mt-10 grid max-w-3xl grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4">
        {CHANNELS.map(({ key, live }, i) => {
          const name = C.names[key];
          return (
            <li key={key}>
              <Reveal delay={i * 70} className="flex h-full flex-col rounded-2xl bg-surface p-4 ring-1 ring-line sm:p-5">
                <div className="flex items-start justify-between gap-2">
                  <span aria-hidden className="flex size-11 items-center justify-center rounded-xl bg-fill text-ink-900">
                    <ChannelMark channel={key} className="size-[22px]" />
                  </span>
                  <span
                    className={cx(
                      "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-bold",
                      live ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500",
                    )}
                  >
                    {live && <span aria-hidden className="size-1.5 rounded-full bg-emerald-500" />}
                    {live ? C.live : C.soon}
                  </span>
                </div>
                <h3 className="mt-4 font-bold text-ink-950">{name}</h3>
                <div className="mt-auto pt-4">
                  {live ? (
                    <Link to="/register" className={buttonClass("secondary", "sm", "w-full")}>
                      {C.connect(name)}
                    </Link>
                  ) : (
                    <span aria-disabled className={buttonClass("secondary", "sm", "w-full cursor-default opacity-55")}>
                      {C.connect(name)}
                    </span>
                  )}
                </div>
              </Reveal>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

function Problem() {
  const { t } = useI18n();
  const p = t.landing.problem;
  const icons = [<Clock key="c" />, <BookOpenCheck key="b" />, <Hand key="h" />];
  return (
    <Section id="why">
      <div className="grid grid-cols-1 items-center gap-x-16 gap-y-12 lg:grid-cols-2">
        <div>
          <SectionHeader id="why" eyebrow={p.eyebrow} title={p.title} lead={p.lead} align="start" />
          <ul className="mt-10 space-y-6">
            {p.points.map((pt, i) => (
              <li key={pt.title}>
                <Reveal delay={i * 90} className="flex gap-4">
                  <span aria-hidden className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700 [&>svg]:size-5">
                    {icons[i]}
                  </span>
                  <div>
                    <h3 className="font-bold text-ink-950">{pt.title}</h3>
                    <p className="mt-1 text-[15px] leading-7 text-slate-600">{pt.body}</p>
                  </div>
                </Reveal>
              </li>
            ))}
          </ul>
        </div>
        <NightInbox />
      </div>
    </Section>
  );
}

/** Last night's unread messages flip to "answered" one by one as the card scrolls in. */
function NightInbox() {
  const { t } = useI18n();
  const p = t.landing.problem;
  const ref = useRef<HTMLDivElement>(null);
  const on = useInView(ref);
  return (
    <Reveal>
      <div ref={ref} className="overflow-hidden rounded-2xl bg-surface shadow-lift ring-1 ring-line">
        <div className="flex items-center gap-2.5 border-b border-slate-100 px-5 py-3.5">
          <span aria-hidden className="flex size-8 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
            <Inbox className="size-4" />
          </span>
          <h3 className="flex-1 text-sm font-bold">{p.inboxTitle}</h3>
        </div>
        <ul className="divide-y divide-slate-100">
          {p.questions.map((q, i) => (
            <li key={q.q} className="flex items-center gap-3 px-5 py-3.5">
              <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-400">
                <UserRound className="size-4" />
              </span>
              <span className="min-w-0 flex-1">
                <span
                  className={cx("block truncate text-sm transition-[color,font-weight] duration-500", on ? "font-medium text-slate-600" : "font-bold text-ink-950")}
                  style={{ transitionDelay: on ? `${500 + i * 380}ms` : undefined }}
                >
                  {q.q}
                </span>
                <span className="num block text-xs text-slate-400">{q.time}</span>
              </span>
              <span className="relative flex h-6 w-24 shrink-0 items-center justify-end">
                <Status on={!on} delay={500 + i * 380} className="text-brand-700">
                  <span aria-hidden className="size-2 rounded-full bg-brand-600" />
                  {p.unread}
                </Status>
                <Status on={on} delay={500 + i * 380} className="text-emerald-700">
                  <Check className="size-3.5" strokeWidth={3} aria-hidden />
                  {p.answered}
                </Status>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Reveal>
  );
}

function Status({ on, delay, className, children }: { on: boolean; delay: number; className?: string; children: ReactNode }) {
  return (
    <span
      aria-hidden={!on}
      className={cx(
        "absolute inset-y-0 end-0 flex items-center gap-1.5 whitespace-nowrap text-xs font-semibold transition-[opacity,transform] duration-500",
        on ? "opacity-100" : "translate-y-1 opacity-0",
        className,
      )}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </span>
  );
}

function Features() {
  const { t } = useI18n();
  const F = t.landing.features;
  const rows: { key: string; icon: ReactNode; copy: { title: string; body: string; bullets: readonly string[] }; demo: ReactNode }[] = [
    { key: "knowledge", icon: <BookOpen />, copy: F.knowledge, demo: <KnowledgeDemo /> },
    { key: "products", icon: <PackageSearch />, copy: F.products, demo: <ProductsDemo /> },
    { key: "handoff", icon: <BellRing />, copy: F.handoff, demo: <HandoffDemo /> },
    { key: "control", icon: <SlidersHorizontal />, copy: F.control, demo: <ToneDemo /> },
  ];
  return (
    <Section id="features" tone="tint">
      <SectionHeader id="features" eyebrow={F.eyebrow} title={F.title} lead={F.lead} />
      <div className="mt-16 space-y-20 lg:mt-24 lg:space-y-28">
        {rows.map((row, i) => (
          <article key={row.key} className="grid grid-cols-1 items-center gap-x-16 gap-y-10 lg:grid-cols-2">
            <Reveal className={cx("max-w-xl", i % 2 === 1 && "lg:order-last")}>
              <span aria-hidden className="flex size-12 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-md shadow-brand-600/25 [&>svg]:size-6">
                {row.icon}
              </span>
              <h3 className="t-h3 mt-6 text-ink-950">{row.copy.title}</h3>
              <p className="mt-3 text-[16px] leading-8 text-slate-600">{row.copy.body}</p>
              <Bullets items={row.copy.bullets} className="mt-6" />
            </Reveal>
            <Reveal delay={120} className="mx-auto w-full max-w-lg">
              {row.demo}
            </Reveal>
          </article>
        ))}
      </div>
    </Section>
  );
}

function How() {
  const { t, f } = useI18n();
  const H = t.landing.how;
  const ref = useRef<HTMLOListElement>(null);
  const on = useInView(ref);
  return (
    <Section id="how">
      <SectionHeader id="how" eyebrow={H.eyebrow} title={H.title} lead={H.lead} />
      <ol ref={ref} className="relative mx-auto mt-16 grid max-w-md grid-cols-1 gap-10 lg:mt-20 lg:max-w-none lg:grid-cols-4 lg:gap-8">
        {/* progress line through the step numbers: vertical on phones, horizontal on desktop */}
        <span
          aria-hidden
          className={cx(
            "absolute start-[1.4375rem] top-6 bottom-6 w-0.5 origin-top bg-brand-200 transition-transform duration-[1400ms] ease-[var(--ease-out-soft)]",
            "lg:start-[12.5%] lg:end-[12.5%] lg:bottom-auto lg:h-0.5 lg:w-auto lg:origin-left rtl:lg:origin-right",
            on ? "scale-100" : "scale-y-0 lg:scale-x-0 lg:scale-y-100",
          )}
        />
        {H.steps.map((step, i) => (
          <li key={step.title} className="relative flex gap-5 lg:flex-col lg:items-center lg:text-center">
            <span
              className={cx(
                "num relative flex size-12 shrink-0 items-center justify-center rounded-full text-lg font-extrabold ring-4 ring-surface transition-colors duration-500",
                on ? "bg-brand-600 text-white" : "bg-brand-50 text-brand-700",
              )}
              style={{ transitionDelay: `${250 + i * 300}ms` }}
            >
              {f.num(i + 1)}
            </span>
            <Reveal delay={150 + i * 120}>
              <h3 className="text-lg font-bold text-ink-950 lg:mt-5">{step.title}</h3>
              <p className="mt-1.5 text-[15px] leading-7 text-slate-600">{step.body}</p>
            </Reveal>
          </li>
        ))}
      </ol>
      <Reveal className="mt-14 flex justify-center">
        <Link to="/register" className={buttonClass("primary", "lg")}>
          {t.landing.nav.start}
          <Arrow />
        </Link>
      </Reveal>
    </Section>
  );
}

function Trust() {
  const { t } = useI18n();
  const T = t.landing.trust;
  const icons = [<ShieldCheck key="s" />, <KeyRound key="k" />, <EyeOff key="e" />, <Trash key="t" />];
  return (
    <Section id="trust" tone="ink">
      <SectionHeader id="trust" eyebrow={T.eyebrow} title={T.title} lead={T.lead} dark />
      <ul className="mt-14 grid grid-cols-1 gap-x-10 gap-y-10 sm:grid-cols-2 lg:mt-16 lg:grid-cols-4">
        {T.items.map((item, i) => (
          <li key={item.title}>
            <Reveal delay={i * 90} className="h-full border-t border-white/15 pt-6">
              <span aria-hidden className="flex size-10 items-center justify-center rounded-xl bg-white/10 text-accent-300 [&>svg]:size-5">
                {icons[i]}
              </span>
              <h3 className="mt-5 font-bold text-white">{item.title}</h3>
              <p className="mt-2 text-[15px] leading-7 text-white/65">{item.body}</p>
            </Reveal>
          </li>
        ))}
      </ul>
      <Reveal className="mt-12 text-center">
        <Link
          to="/privacy"
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-white/85 underline decoration-white/30 underline-offset-4 transition-colors hover:text-white hover:decoration-white"
        >
          {T.privacyLink}
          <ArrowRight className="size-4 rtl:-scale-x-100" aria-hidden />
        </Link>
      </Reveal>
    </Section>
  );
}

function Faq() {
  const { t } = useI18n();
  const Q = t.landing.faq;
  return (
    <Section id="faq">
      <div className="grid grid-cols-1 gap-x-16 gap-y-10 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <SectionHeader id="faq" eyebrow={Q.eyebrow} title={Q.title} align="start" className="lg:sticky lg:top-28 lg:self-start" />
        <Reveal>
          <div className="divide-y divide-slate-200 border-y border-slate-200">
            {Q.items.map((item) => (
              <details key={item.q} name="faq" className="group">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 text-start text-[17px] font-bold text-ink-950 transition-colors hover:text-brand-700 [&::-webkit-details-marker]:hidden">
                  {item.q}
                  <span
                    aria-hidden
                    className="flex size-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500 transition-[transform,background-color,color] duration-300 group-open:rotate-180 group-open:bg-brand-600 group-open:text-white"
                  >
                    <ChevronDown className="size-4" />
                  </span>
                </summary>
                <p className="animate-pop-in pb-6 pe-12 text-[15px] leading-8 text-slate-600">{item.a}</p>
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
      <Reveal className="container-site relative flex flex-col items-center py-[clamp(4.5rem,10vw,7.5rem)] text-center">
        <LogoMark px={64} className="shadow-float ring-2 ring-white/25" />
        <h2 id="cta-title" className="t-h2 mt-8 max-w-2xl text-balance">
          {C.title}
        </h2>
        <p className="t-lead mt-4 max-w-xl text-pretty text-white/80">{C.lead}</p>
        <div className="mt-9 flex w-full flex-col justify-center gap-3 sm:w-auto sm:flex-row">
          <Link to="/register" className={buttonClass("inverse", "lg")}>
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
