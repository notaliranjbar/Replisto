import { Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import {
  BarChart3,
  BellRing,
  BookOpen,
  CalendarClock,
  Camera,
  FlaskConical,
  Gift,
  HelpCircle,
  Inbox,
  Languages,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageCircleMore,
  MessageCircleQuestion,
  Package,
  Settings,
  UserRound,
  Wallet,
  X,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { keys, useDashboard, useMe } from "../api/queries";
import { AskReplistoLauncher } from "./AskReplisto";
import { useAuth } from "../auth/AuthContext";
import { otherLang, useI18n } from "../i18n";
import { useHandoffWatcher } from "../lib/notifications";
import { Logo, LogoMark } from "./Logo";
import ThemeToggle from "./ThemeToggle";
import { CountBadge, PageLoading, cx } from "./ui";

type Item = { to: string; label: string; icon: ReactNode; badge?: number; badgeTone?: "red" | "neutral"; end?: boolean; tag?: string };
type Group = { label?: string; items: Item[] };

/**
 * The logged-in shell. Desktop: a dark navy sidebar beside a light grey canvas. Phones: a slim top bar, a bottom tab bar for the everyday screens and a drawer
 * with everything else. Full-height pages size themselves with --chrome-top/--chrome-bottom.
 */
export default function Layout() {
  const { t, f, lang } = useI18n();
  const { data: me } = useMe();
  const { data: dash } = useDashboard();
  const gift = dash?.wallet.gift;
  const giftWaiting = !!dash?.wallet.enabled && !!gift && !gift.granted && gift.amount_cents > 0;
  const [drawer, setDrawer] = useState(false);
  const location = useLocation();

  useHandoffWatcher(dash);

  // The shop remembers the panel's language: the bot writes handoff reasons and summaries
  // for the owner in it. On a switch, reload server text so it comes back in the new language.
  const qc = useQueryClient();
  const firstLang = useRef(lang);
  useEffect(() => {
    if (firstLang.current !== lang) {
      firstLang.current = lang;
      qc.invalidateQueries();
    }
    // The browser's time zone: insights read "best hours to post" in the owner's local time.
    let timezone: string | undefined;
    try {
      timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    } catch {
      timezone = undefined;
    }
    const zoneChanged = !!me && !!timezone && me.shop.timezone !== timezone;
    if (me && (me.shop.language !== lang || zoneChanged)) {
      api("/shop", { method: "PATCH", json: { language: lang, ...(zoneChanged ? { timezone } : {}) } })
        .then(() => qc.invalidateQueries({ queryKey: keys.me }))
        .catch(() => {
          // not important enough to bother the owner; retried on the next visit
        });
    }
  }, [lang, me, qc]);

  // Close the mobile drawer on navigation
  useEffect(() => setDrawer(false), [location.pathname]);

  // "(2) Layla Boutique panel" in the browser tab
  useEffect(() => {
    const base = me ? t.panelTitle(me.shop.name) : t.appName;
    const n = dash?.open_handoffs ?? 0;
    document.title = n > 0 ? `(${f.num(n)}) ${base}` : base;
  }, [me, dash, t, f]);

  const groups: Group[] = [
    { items: [{ to: "/", label: t.nav.dashboard, icon: <LayoutDashboard />, end: true }] },
    {
      label: t.panel.nav.groupMessages,
      items: [
        { to: "/handoffs", label: t.nav.handoffs, icon: <BellRing />, badge: dash?.open_handoffs },
        { to: "/inbox", label: t.nav.inbox, icon: <Inbox /> },
        { to: "/comments", label: t.social.nav.comments, icon: <MessageCircleMore />, badge: dash?.social.comments_waiting },
        { to: "/unanswered", label: t.nav.unanswered, icon: <HelpCircle />, badge: dash?.last_7_days.open_unanswered, badgeTone: "neutral" },
      ],
    },
    {
      label: t.social.nav.groupGrow,
      items: [
        { to: "/stories", label: t.social.nav.stories, icon: <CalendarClock /> },
        { to: "/insights", label: t.social.nav.insights, icon: <BarChart3 /> },
      ],
    },
    {
      label: t.panel.nav.groupTrain,
      items: [
        { to: "/knowledge", label: t.nav.knowledge, icon: <BookOpen /> },
        { to: "/products", label: t.nav.products, icon: <Package />, badge: dash?.pending_proposals, badgeTone: "neutral" },
        { to: "/playground", label: t.nav.playground, icon: <FlaskConical /> },
      ],
    },
    {
      label: t.panel.nav.groupSetup,
      items: [
        { to: "/settings", label: t.nav.settings, icon: <Settings /> },
        { to: "/billing", label: t.launch.nav.billing, icon: <Wallet /> },
        { to: "/instagram", label: t.nav.instagram, icon: <Camera />, tag: dash && !dash.setup.instagram_available ? t.launch.nav.soon : undefined },
        { to: "/account", label: t.nav.account, icon: <UserRound /> },
        { to: "/help", label: t.launch.ask.launcher, icon: <MessageCircleQuestion /> },
      ],
    },
  ];

  return (
    <div className="min-h-dvh bg-canvas [--chrome-bottom:4.25rem] [--chrome-top:4rem] lg:flex lg:[--chrome-bottom:0rem] lg:[--chrome-top:0rem]">
      <aside className="sticky top-0 hidden h-dvh w-[16.5rem] shrink-0 border-e border-white/[0.06] bg-night-950 lg:block">
        <Sidebar groups={groups} />
      </aside>

      <MobileTopBar onMenu={() => setDrawer(true)} alert={!!dash?.open_handoffs} />

      <main className="min-w-0 flex-1 pb-[var(--chrome-bottom)]">
        <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-10 lg:py-10">
          {/* pages load on demand; the shell stays put meanwhile */}
          {giftWaiting && location.pathname !== "/" && (
            <Link
              to="/"
              className="mb-6 flex flex-wrap items-center gap-3 rounded-lg border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-ink-900 transition-colors hover:bg-brand-100"
            >
              <Gift className="size-5 shrink-0 text-brand-600" aria-hidden />
              <span className="min-w-0 flex-1">{t.launch.gift.banner(f.usd(gift.amount_cents))}</span>
              <span className="font-semibold text-brand-700">{t.launch.gift.bannerAction}</span>
            </Link>
          )}
          {/* a brand-new shop has no credit yet: the gift banner/card says how to get it instead */}
          {dash?.wallet.enabled && dash.wallet.low_balance && !giftWaiting && location.pathname !== "/billing" && (
            <Link
              to="/billing"
              className="mb-6 flex flex-wrap items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 transition-colors hover:bg-amber-100"
            >
              <Wallet className="size-5 shrink-0 text-amber-500" aria-hidden />
              <span className="min-w-0 flex-1">
                {dash.wallet.balance_cents <= 0 ? t.launch.emptyBalance : t.launch.lowBalance(f.usd(dash.wallet.balance_cents))}
              </span>
              <span className="font-semibold">{t.launch.topUpNow}</span>
            </Link>
          )}
          <Suspense fallback={<PageLoading />}>
            <Outlet />
          </Suspense>
        </div>
      </main>

      {/* desktop only: on phones it's the "Ask Replisto" page in the menu, so nothing covers content */}
      {!["/playground", "/help"].includes(location.pathname) && (
        <div className="hidden lg:block">
          <AskReplistoLauncher />
        </div>
      )}
      <BottomTabs handoffs={dash?.open_handoffs} onMore={() => setDrawer(true)} />
      <Drawer open={drawer} onClose={() => setDrawer(false)} groups={groups} />
    </div>
  );
}

function Sidebar({ groups, onClose }: { groups: Group[]; onClose?: () => void }) {
  const { t, f, lang, toggleLang } = useI18n();
  const { logout } = useAuth();
  const { data: me } = useMe();
  const { data: dash } = useDashboard();
  const botOn = dash?.setup.bot_enabled;

  return (
    <div className="flex h-full flex-col text-white">
      <div className="flex h-16 shrink-0 items-center justify-between px-5">
        <Link to="/" className="rounded-lg">
          <Logo tone="dark" />
        </Link>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label={t.panel.nav.closeMenu}
            data-autofocus
            className="-me-2 inline-flex size-10 items-center justify-center rounded-lg text-white/60 transition-colors hover:bg-white/10 hover:text-white"
          >
            <X className="size-5" aria-hidden />
          </button>
        )}
      </div>

      {/* which shop, and whether the bot is answering right now */}
      <div className="mx-3 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2.5">
        <div className="truncate text-sm font-semibold">{me?.shop.name ?? t.appName}</div>
        <Link to="/settings" className="mt-1 inline-flex items-center gap-2 text-xs font-medium text-white/55 transition-colors hover:text-white">
          <span className="relative flex size-2" aria-hidden>
            {botOn && <span className="absolute inset-0 animate-ping rounded-full bg-emerald-400 opacity-60 [animation-duration:2s]" />}
            <span className={cx("relative size-2 rounded-full", botOn ? "bg-emerald-400" : "bg-white/30")} />
          </span>
          {dash ? (botOn ? t.nav.botOnShort : t.nav.botOffShort) : " "}
        </Link>
      </div>

      <nav aria-label={t.panel.nav.main} className="scroll-dark mt-1 flex-1 overflow-y-auto px-3 pb-4">
        {groups.map((g, i) => (
          <div key={i} className="mt-4">
            {g.label && <div className="mb-1 px-3 text-[11px] font-medium uppercase tracking-wider text-white/40">{g.label}</div>}
            <ul className="space-y-0.5">
              {g.items.map((it) => (
                <li key={it.to}>
                  <NavLink
                    to={it.to}
                    end={it.end}
                    className={({ isActive }) =>
                      cx(
                        "relative flex h-9 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors duration-150",
                        "[&>svg]:size-[18px] [&>svg]:shrink-0",
                        isActive
                          ? "bg-white/10 text-white before:absolute before:inset-y-2 before:start-0 before:w-[3px] before:rounded-e before:bg-brand-400 rtl:before:rounded-e-none rtl:before:rounded-s [&>svg]:text-brand-300"
                          : "text-white/65 hover:bg-white/[0.06] hover:text-white",
                      )
                    }
                  >
                    {it.icon}
                    <span className="flex-1 truncate">{it.label}</span>
                    {it.tag && <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-medium text-white/60">{it.tag}</span>}
                    {!!it.badge && <CountBadge count={f.num(it.badge)} tone={it.badgeTone} />}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="shrink-0 space-y-0.5 border-t border-white/10 p-3 text-sm">
        <ThemeToggle label className="h-9 w-full rounded-md px-3 font-medium text-white/65 hover:bg-white/[0.06] hover:text-white" />
        <button
          type="button"
          onClick={toggleLang}
          className="flex h-9 w-full items-center gap-3 rounded-md px-3 font-medium text-white/65 transition-colors hover:bg-white/[0.06] hover:text-white"
        >
          <Languages className="size-[18px]" aria-hidden />
          <span lang={otherLang(lang)}>{t.otherLang}</span>
        </button>
        <button
          type="button"
          onClick={logout}
          className="flex h-9 w-full items-center gap-3 rounded-md px-3 font-medium text-white/65 transition-colors hover:bg-white/[0.06] hover:text-white"
        >
          <LogOut className="size-[18px] rtl:-scale-x-100" aria-hidden />
          {t.common.logout}
        </button>
        <Link to="/privacy" className="block px-3 pt-2 text-xs text-white/40 transition-colors hover:text-white/70">
          {t.nav.legal}
        </Link>
      </div>
    </div>
  );
}

function MobileTopBar({ onMenu, alert }: { onMenu: () => void; alert: boolean }) {
  const { t } = useI18n();
  const { data: me } = useMe();
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-200/80 bg-surface/90 px-4 backdrop-blur-md lg:hidden">
      <Link to="/" aria-label={t.landing.nav.home} className="rounded-lg">
        <LogoMark px={30} />
      </Link>
      <span dir="auto" className="min-w-0 flex-1 truncate text-start font-semibold text-ink-950">
        {me?.shop.name ?? t.appName}
      </span>
      <ThemeToggle className="size-11 justify-center rounded-lg text-slate-600 hover:bg-slate-100 hover:text-ink-950" />
      <button
        type="button"
        onClick={onMenu}
        aria-label={t.nav.menu}
        className="relative -me-2 inline-flex size-11 items-center justify-center rounded-lg text-ink-900 transition-colors hover:bg-slate-100"
      >
        <Menu className="size-6" aria-hidden />
        {alert && <span className="absolute end-2 top-2 size-2.5 rounded-full bg-red-500 ring-2 ring-surface" />}
      </button>
    </header>
  );
}

/** Phones: the four screens owners open every day, plus "more" for the drawer. */
function BottomTabs({ handoffs, onMore }: { handoffs?: number; onMore: () => void }) {
  const { t, f } = useI18n();
  const N = t.panel.nav;
  const tabs = [
    { to: "/", label: N.home, icon: <LayoutDashboard />, end: true },
    { to: "/handoffs", label: N.handoffs, icon: <BellRing />, badge: handoffs },
    { to: "/inbox", label: N.inbox, icon: <Inbox /> },
    { to: "/playground", label: N.test, icon: <FlaskConical /> },
  ];
  const cls = "relative flex flex-1 flex-col items-center justify-center gap-1 text-[11px] font-medium transition-colors [&>svg]:size-[21px]";
  return (
    <nav
      aria-label={N.main}
      className="fixed inset-x-0 bottom-0 z-30 flex h-[var(--chrome-bottom)] border-t border-slate-200/80 bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden"
    >
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={({ isActive }) =>
            cx(
              cls,
              isActive ? "text-brand-600 dark:text-brand-700" : "text-slate-500 hover:text-ink-900",
            )
          }
        >
          {tab.icon}
          {tab.label}
          {!!tab.badge && (
            <span className="num absolute start-1/2 top-2 ms-2 min-w-4 rounded-full bg-red-500 px-1 text-center text-[10px] leading-4 text-white ring-2 ring-surface">
              {f.num(tab.badge)}
            </span>
          )}
        </NavLink>
      ))}
      <button type="button" onClick={onMore} className={cx(cls, "text-slate-500 hover:text-ink-900")}>
        <Menu aria-hidden />
        {N.more}
      </button>
    </nav>
  );
}

function Drawer({ open, onClose, groups }: { open: boolean; onClose: () => void; groups: Group[] }) {
  const ref = useRef<HTMLDialogElement>(null);

  // native modal dialog: focus trap, Esc and an inert page for free
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      d.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    }
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className="m-0 h-dvh max-h-none w-full max-w-none bg-transparent p-0 open:animate-none backdrop:bg-night-950/50 lg:hidden"
    >
      {open && (
        <aside className="animate-sheet-in h-full w-[18rem] max-w-[85%] bg-night-950 shadow-float">
          <Sidebar groups={groups} onClose={onClose} />
        </aside>
      )}
    </dialog>
  );
}
