import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  BellRing,
  Bot,
  BookOpen,
  CalendarClock,
  Check,
  FlaskConical,
  HelpCircle,
  Inbox,
  MessageCircleMore,
  MessagesSquare,
  SlidersHorizontal,
  Sparkles,
  UserRound,
  Users,
  Wallet,
} from "lucide-react";
import { api } from "../api/client";
import { keys, useDashboard, useMe } from "../api/queries";
import type { Shop } from "../api/types";
import { useToast } from "../components/toast";
import { EmailNotVerified, GiftCard } from "../components/verify";
import { Alert, Card, CardHeader, ConfirmDialog, IconChip, LinkButton, PageLoading, Toggle, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";
import { getFlag, playgroundKey } from "../lib/storage";

export default function Dashboard() {
  const { t, f } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const { data, isPending, error, refetch } = useDashboard();
  const { data: me } = useMe();
  const [confirmOn, setConfirmOn] = useState(false);

  const toggleBot = useMutation({
    mutationFn: (enabled: boolean) => api<Shop>("/shop", { method: "PATCH", json: { bot_enabled: enabled } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.dashboard });
      qc.invalidateQueries({ queryKey: keys.shop });
      qc.invalidateQueries({ queryKey: keys.me });
      setConfirmOn(false);
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  if (isPending) return <PageLoading />;
  if (error) return <Alert kind="error" action={<button onClick={() => refetch()} className="font-semibold underline">{t.common.retry}</button>}>{errorMessage(error, t)}</Alert>;

  const s = data.setup;
  const L = t.launch.dashboard;
  const igOk = s.instagram_connected && s.instagram_active;
  const channelOk = igOk;
  const tried = me ? getFlag(playgroundKey(me.shop.id)) : false;

  const steps: Step[] = [
    { done: s.knowledge_entries > 0, title: t.dashboard.stepKnowledge, hint: t.dashboard.stepKnowledgeHint, to: "/knowledge" },
    { done: s.product_count > 0, title: L.stepTeach, hint: L.stepTeachHint, to: "/products" },
    { done: tried, title: t.dashboard.stepPlayground, hint: t.dashboard.stepPlaygroundHint, to: "/playground" },
    { done: s.bot_enabled, title: t.dashboard.stepBot, hint: t.dashboard.stepBotHint },
  ];
  if (s.instagram_available) {
    steps.unshift({ done: igOk, title: t.dashboard.stepInstagram, hint: t.dashboard.stepInstagramHint, to: "/instagram" });
  }
  // the optional products step doesn't keep the checklist on screen
  const allDone = steps.every((x) => x.done || x.optional);

  const stats = data.last_7_days;
  const hasActivity = stats.conversations + stats.customer_messages + stats.bot_replies > 0;

  function setBot(on: boolean) {
    if (on && (!channelOk || s.knowledge_entries === 0)) setConfirmOn(true);
    else toggleBot.mutate(on);
  }

  return (
    <div className="space-y-6">
      <StatusHero
        name={me?.full_name || me?.shop.name || t.appName}
        on={s.bot_enabled}
        username={s.instagram_available ? s.instagram_username : null}
        toggle={<Toggle checked={s.bot_enabled} onChange={setBot} disabled={toggleBot.isPending} label={t.dashboard.botStatus} />}
      />

      {data.open_handoffs > 0 && (
        <Link
          to="/handoffs"
          className="group flex flex-wrap items-center gap-4 rounded-xl border border-red-200 border-s-4 border-s-red-500 bg-surface p-4 shadow-soft transition-colors hover:bg-red-50 sm:p-5"
        >
          <span className="flex size-10 items-center justify-center rounded-lg bg-red-50 text-red-600">
            <BellRing className="size-5 origin-top group-hover:animate-[bell_0.6s_ease-in-out]" aria-hidden />
          </span>
          {/* a real minimum width so the button wraps below on phones instead of squeezing the text */}
          <div className="min-w-52 flex-1">
            <div className="font-semibold tracking-tight text-ink-950">{t.dashboard.waitingCard(f.num(data.open_handoffs))}</div>
            <div className="mt-0.5 text-sm text-slate-500">{t.dashboard.waitingCardHint}</div>
          </div>
          <span className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-red-600 px-3.5 text-sm font-medium text-white">
            {t.dashboard.waitingCardAction}
            <ArrowLeft className="size-4 transition-transform group-hover:-translate-x-0.5 ltr:rotate-180 ltr:group-hover:translate-x-0.5" aria-hidden />
          </span>
        </Link>
      )}

      {data.pending_proposals > 0 && (
        <Alert kind="info" action={<LinkButton to="/products" size="sm" variant="secondary">{L.pendingAction}</LinkButton>}>
          {L.pending(f.num(data.pending_proposals))}
        </Alert>
      )}
      {s.instagram_available && s.instagram_connected && !s.instagram_active && (
        <Alert kind="warning" action={<LinkButton to="/instagram" size="sm" variant="secondary">{t.dashboard.alertIgInactiveAction}</LinkButton>}>
          {t.dashboard.alertIgInactive}
        </Alert>
      )}
      {s.product_error && (
        <Alert kind="warning" action={<LinkButton to="/products" size="sm" variant="secondary">{t.dashboard.alertProductsAction}</LinkButton>}>
          {s.product_error}
        </Alert>
      )}
      {!s.ai_ready && <Alert kind="info">{t.dashboard.alertAi}</Alert>}
      {me && <EmailNotVerified me={me} />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          <GiftCard gift={data.wallet.gift} />
          {!allDone && <Checklist steps={steps} botOn={s.bot_enabled} setBot={setBot} busy={toggleBot.isPending} />}

          {/* A brand-new shop sees only the checklist, not a wall of zeros. */}
          {(allDone || hasActivity) && (
            <section aria-labelledby="stats-title">
              <h2 id="stats-title" className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
                {t.dashboard.last7Days}
              </h2>
              <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
                <Stat icon={<MessagesSquare />} label={t.dashboard.statConversations} value={f.num(stats.conversations)} to="/inbox" />
                <Stat icon={<UserRound />} label={t.dashboard.statCustomerMessages} value={f.num(stats.customer_messages)} />
                <Stat icon={<Bot />} label={t.dashboard.statBotReplies} value={f.num(stats.bot_replies)} />
                <Stat icon={<HelpCircle />} label={t.dashboard.statOpenUnanswered} value={f.num(stats.open_unanswered)} to="/unanswered" warn={stats.open_unanswered > 0} />
              </div>
            </section>
          )}

          {s.instagram_connected && (
            <section aria-labelledby="social-title">
              <h2 id="social-title" className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
                {t.social.dashboard.title}
              </h2>
              <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
                <Stat
                  icon={<MessageCircleMore />}
                  label={t.social.comments.statWaiting}
                  value={f.num(data.social.comments_waiting)}
                  to="/comments"
                  warn={data.social.comments_waiting > 0}
                />
                <Stat icon={<Check />} label={t.social.comments.statAnswered} value={f.num(data.social.comments_answered_7_days)} to="/comments" />
                <Stat
                  icon={<CalendarClock />}
                  label={data.social.next_story_at ? t.social.stories.nextAt(f.smart(data.social.next_story_at)) : t.social.stories.statScheduled}
                  value={f.num(data.social.stories_scheduled)}
                  to="/stories"
                />
                <Stat
                  icon={data.social.followers !== null && data.social.followers !== undefined ? <Users /> : <BarChart3 />}
                  label={data.social.followers !== null && data.social.followers !== undefined ? t.social.dashboard.followers : t.social.insights.title}
                  value={data.social.followers !== null && data.social.followers !== undefined ? f.num(data.social.followers) : "—"}
                  to="/insights"
                />
              </div>
            </section>
          )}
        </div>

        <aside className="min-w-0 space-y-6">
          <Shortcuts />
          <Link to="/billing" className={cx("flex items-center gap-4 rounded-xl border bg-surface p-5 shadow-soft transition-colors hover:border-slate-300", data.wallet.low_balance ? "border-amber-300" : "border-slate-200")}>
            <IconChip tone={data.wallet.low_balance ? "amber" : "brand"}>
              <Wallet />
            </IconChip>
            <div className="min-w-0 flex-1">
              <div className="text-sm text-slate-500">{L.walletTitle}</div>
              <div className="mt-0.5 font-semibold text-ink-950">
                <span className="num text-xl">{f.usd(data.wallet.balance_cents)}</span>
              </div>
            </div>
            <span className="text-xs font-semibold text-brand-700">{L.walletAction}</span>
          </Link>
          <Card className="flex items-center gap-4 p-5">
            <IconChip>
              <Sparkles />
            </IconChip>
            <div className="min-w-0">
              <div className="text-sm text-slate-500">{t.panel.dashboard.usageTitle}</div>
              <div className="mt-0.5 font-semibold text-ink-950">
                <span className="num text-xl">{f.num(data.tokens_this_month)}</span> <span className="text-sm font-medium text-slate-500">{t.dashboard.tokensUnit}</span>
              </div>
            </div>
          </Card>
        </aside>
      </div>

      <ConfirmDialog
        open={confirmOn}
        onClose={() => setConfirmOn(false)}
        onConfirm={() => toggleBot.mutate(true)}
        loading={toggleBot.isPending}
        title={t.dashboard.botTurnOnConfirmTitle}
        body={
          <ul className="list-disc space-y-1 ps-5">
            {!channelOk && <li>{s.instagram_available ? t.dashboard.botTurnOnConfirmIg : t.launch.instagramSoon.body}</li>}
            {s.knowledge_entries === 0 && <li>{t.dashboard.botTurnOnConfirmKnowledge}</li>}
          </ul>
        }
        confirmLabel={t.dashboard.botTurnOnAnyway}
        cancelLabel={t.common.cancel}
      />
    </div>
  );
}

/** Greeting and the bot's master switch: a plain white card with a status row. */
function StatusHero({ name, on, username, toggle }: { name: string; on: boolean; username: string | null; toggle: ReactNode }) {
  const { t } = useI18n();
  return (
    <section aria-labelledby="dash-title" className="overflow-hidden rounded-xl border border-slate-200 bg-surface shadow-soft">
      <div className="flex flex-wrap items-end justify-between gap-4 p-5 sm:p-6">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">{t.dashboard.title}</p>
          <h1 id="dash-title" className="mt-1 text-[1.375rem] font-semibold tracking-tight text-ink-950 sm:text-2xl">
            {t.panel.dashboard.greeting(name)}
          </h1>
        </div>
        {username && (
          <a href={`https://instagram.com/${username}`} target="_blank" rel="noopener noreferrer" className="ltr text-sm font-medium text-slate-500 hover:text-brand-700 hover:underline">
            @{username}
          </a>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-t border-slate-200 bg-slate-50 px-5 py-3.5 sm:px-6">
        <div className="min-w-0">
          <span className="inline-flex items-center gap-2 text-sm font-medium text-ink-900">
            <span className="relative flex size-2" aria-hidden>
              {on && <span className="absolute inset-0 animate-ping rounded-full bg-emerald-400 opacity-70 [animation-duration:2s]" />}
              <span className={cx("relative size-2 rounded-full", on ? "bg-emerald-500" : "bg-slate-400")} />
            </span>
            {on ? t.dashboard.botOn : t.dashboard.botOff}
          </span>
          {!on && <p className="mt-1 text-sm text-slate-500">{t.panel.dashboard.offHint}</p>}
        </div>
        <label className="flex items-center gap-3">
          <span className="text-sm font-medium text-slate-600">{t.dashboard.botStatus}</span>
          {toggle}
        </label>
      </div>
    </section>
  );
}

type Step = { done: boolean; title: string; hint: string; to?: string; optional?: boolean };

/** Setup as a vertical stepper, drawn like the site's "four steps" section. */
function Checklist({ steps, botOn, setBot, busy }: { steps: Step[]; botOn: boolean; setBot: (on: boolean) => void; busy: boolean }) {
  const { t, f } = useI18n();
  const doneCount = steps.filter((x) => x.done).length;
  const current = steps.findIndex((x) => !x.done);
  return (
    <Card>
      <div className="border-b border-slate-100 px-5 py-4 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold text-ink-950">{t.dashboard.checklistTitle}</h2>
          <span className="text-sm font-medium text-slate-500">{t.dashboard.checklistProgress(f.num(doneCount), f.num(steps.length))}</span>
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-fill">
          <div className="h-full rounded-full bg-brand-600 transition-[width] duration-700" style={{ width: `${(doneCount / steps.length) * 100}%` }} />
        </div>
      </div>
      <ol className="px-5 py-3 sm:px-6">
        {steps.map((step, i) => (
          <li key={step.title} className="relative flex items-center gap-4 py-3">
            {/* connector to the next step */}
            {i < steps.length - 1 && <span aria-hidden className="absolute start-[0.9375rem] top-[calc(50%+1.25rem)] h-[calc(100%-2.5rem)] w-0.5 bg-slate-100" />}
            <span
              className={cx(
                "num relative flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
                step.done ? "bg-emerald-500 text-white" : i === current ? "bg-brand-600 text-white ring-4 ring-brand-100" : "bg-surface text-slate-400 ring-2 ring-slate-200",
              )}
            >
              {step.done ? <Check className="size-4" strokeWidth={3} aria-hidden /> : f.num(i + 1)}
            </span>
            <div className="min-w-0 flex-1">
              <div className={cx("font-semibold", step.done ? "text-slate-400" : "text-ink-950")}>
                {step.title}
                {step.optional && <span className="ms-1.5 text-xs font-medium text-slate-400">({t.common.optional})</span>}
              </div>
              {!step.done && <div className="text-sm leading-6 text-slate-500">{step.hint}</div>}
            </div>
            {!step.done &&
              (step.to ? (
                <LinkButton to={step.to} size="sm" variant={i === current ? "primary" : "soft"}>
                  {t.dashboard.doStep}
                </LinkButton>
              ) : (
                <Toggle checked={botOn} onChange={setBot} disabled={busy} label={step.title} />
              ))}
          </li>
        ))}
      </ol>
    </Card>
  );
}

function Stat({ icon, label, value, to, warn }: { icon: ReactNode; label: string; value: string; to?: string; warn?: boolean }) {
  const body = (
    <>
      <IconChip tone={warn ? "amber" : "brand"}>{icon}</IconChip>
      <div className={cx("num mt-4 text-3xl font-semibold tracking-tight", warn ? "text-amber-600" : "text-ink-950")}>{value}</div>
      <div className="mt-0.5 text-sm text-slate-500">{label}</div>
    </>
  );
  const cls = "block rounded-xl border border-slate-200 bg-surface p-5 shadow-soft";
  return to ? (
    <Link to={to} className={cx(cls, "transition-[box-shadow,transform] duration-200 hover:-translate-y-0.5 hover:shadow-lift")}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

function Shortcuts() {
  const { t } = useI18n();
  const Q = t.panel.dashboard.quick;
  const links = [
    { to: "/playground", icon: <FlaskConical />, ...Q.playground },
    { to: "/knowledge", icon: <BookOpen />, ...Q.knowledge },
    { to: "/inbox", icon: <Inbox />, ...Q.inbox },
    { to: "/settings", icon: <SlidersHorizontal />, ...Q.settings },
  ];
  return (
    <Card>
      <CardHeader title={t.panel.dashboard.quickTitle} />
      <ul className="p-2">
        {links.map((l) => (
          <li key={l.to}>
            <Link to={l.to} className="group flex items-center gap-3 rounded-xl p-3 transition-colors hover:bg-brand-50/70">
              <IconChip>{l.icon}</IconChip>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-ink-950">{l.title}</span>
                <span className="block text-xs leading-5 text-slate-500">{l.body}</span>
              </span>
              <ArrowRight className="size-4 text-slate-300 transition-[transform,color] duration-200 group-hover:translate-x-0.5 group-hover:text-brand-700 rtl:-scale-x-100 rtl:group-hover:-translate-x-0.5" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
