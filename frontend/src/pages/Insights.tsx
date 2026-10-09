import { useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3,
  CalendarClock,
  CalendarDays,
  Copy,
  ExternalLink,
  Hash,
  Lightbulb,
  RefreshCw,
  Send,
  Sparkles,
  ThumbsUp,
  TrendingUp,
  Wand2,
} from "lucide-react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { ContentIdea, ContentReport, Insights as InsightsData, InsightsMedia } from "../api/types";
import { AreaChart, BarList, ColumnChart, Delta } from "../components/charts";
import { InstagramNotice, PostThumb } from "../components/social";
import { useToast } from "../components/toast";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, PageHeader, PageLoading, Textarea, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";

export default function Insights() {
  const { t, f } = useI18n();
  const I = t.social.insights;
  const toast = useToast();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: keys.insights, queryFn: () => api<InsightsData>("/insights") });
  const refresh = useMutation({
    mutationFn: () => api<InsightsData>("/insights/refresh", { method: "POST" }),
    onSuccess: (data) => {
      qc.setQueryData(keys.insights, data);
      qc.invalidateQueries({ queryKey: keys.dashboard });
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });
  const data = query.data;

  const action = data?.available && (
    <div className="flex flex-wrap items-center gap-3">
      {data.fetched_at && <span className="text-xs text-slate-500">{I.updated(f.ago(data.fetched_at))}</span>}
      <Button variant="secondary" size="sm" icon={<RefreshCw className={cx("size-4", refresh.isPending && "animate-spin")} />} loading={false} disabled={refresh.isPending} onClick={() => refresh.mutate()}>
        {I.refresh}
      </Button>
    </div>
  );

  return (
    <div className="max-w-6xl">
      <PageHeader icon={<BarChart3 />} title={I.title} subtitle={I.subtitle} action={action} />
      {data && <InstagramNotice connected={data.available || data.needs_reconnect} needsReconnect={data.needs_reconnect} />}
      {query.isPending ? (
        <PageLoading />
      ) : query.error ? (
        <Alert kind="error">{errorMessage(query.error, t)}</Alert>
      ) : !data!.profile || !data!.analysis ? (
        <Card>
          <EmptyState icon={<BarChart3 />} title={I.emptyTitle}>
            <p>{I.emptyBody}</p>
            {data!.available && (
              <Button className="mt-4" loading={refresh.isPending} onClick={() => refresh.mutate()}>
                {I.readFirst}
              </Button>
            )}
          </EmptyState>
        </Card>
      ) : (
        <Overview data={data!} />
      )}
    </div>
  );
}

function useCompact() {
  const { lang } = useI18n();
  return useMemo(() => {
    const fmt = new Intl.NumberFormat(lang === "ar" ? "ar-u-nu-latn" : "en-US", { notation: "compact", maximumFractionDigits: 1 });
    return (v: number) => fmt.format(v);
  }, [lang]);
}

function Overview({ data }: { data: InsightsData }) {
  const { t, f } = useI18n();
  const I = t.social.insights;
  const compact = useCompact();
  const analysis = data.analysis!;
  const profile = data.profile!;
  const change = analysis.week_change;
  const day = (iso: string) => f.shortDay(iso);

  const reach = data.reach_series.map((p) => ({ label: day(p.date), value: p.value, title: f.date(`${p.date}T12:00:00`) }));
  const followers = data.follower_series.map((p) => ({ label: day(p.date), value: p.value, title: f.date(`${p.date}T12:00:00`) }));
  const weekdays = I.daysShort.map((label, i) => ({
    label,
    title: I.days[i],
    value: analysis.weekdays.find((d) => d.day === i)?.avg_engagement ?? 0,
  }));
  const hours = Array.from({ length: 8 }, (_, i) => i * 3).map((h) => ({
    label: `${String(h).padStart(2, "0")}`,
    title: `${String(h).padStart(2, "0")}:00–${String(h + 3).padStart(2, "0")}:00`,
    value: analysis.hours.find((x) => x.from_hour === h)?.avg_engagement ?? 0,
  }));
  const media = new Map(data.media.map((m) => [m.id, m]));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <Kpi label={I.followers} value={f.num(profile.followers)} note={I.newFollowers(f.num(analysis.new_followers_30_days))} />
        <Kpi label={I.reach} value={compact(data.week.reach ?? 0)} delta={change.reach} />
        <Kpi label={I.interactions} value={compact(data.week.total_interactions ?? 0)} delta={change.total_interactions} />
        <Kpi label={I.views} value={compact(data.week.views ?? 0)} delta={change.views} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader icon={<TrendingUp />} title={I.reachChart} subtitle={I.reachChartHint} />
          <div className="p-4 sm:p-5">
            {reach.length > 1 ? <AreaChart points={reach} caption={I.reachChart} format={compact} /> : <p className="text-sm text-slate-500">{I.noNumbers}</p>}
          </div>
        </Card>
        <Card>
          <CardHeader title={I.followersChart} />
          <div className="p-4 sm:p-5">
            {followers.length > 0 ? (
              <ColumnChart points={followers} caption={I.followersChart} format={(v) => f.num(v)} every={Math.ceil(followers.length / 3)} />
            ) : (
              <p className="text-sm text-slate-500">{I.noNumbers}</p>
            )}
          </div>
        </Card>
      </div>

      <section aria-labelledby="works-title">
        <h2 id="works-title" className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-500">
          {I.whatWorks}
        </h2>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <Card>
            <CardHeader title={I.byFormat} subtitle={I.byFormatHint} />
            <div className="p-4 sm:p-5">
              <BarList
                rows={analysis.formats.map((x) => ({
                  key: x.format,
                  label: `${I.formats[x.format as keyof typeof I.formats] ?? x.format} · ${f.num(x.posts)}`,
                  value: x.avg_engagement,
                }))}
                format={compact}
              />
              <p className="mt-4 text-xs leading-5 text-slate-500">
                {I.postsPerWeek(f.num(analysis.posts_per_week))}
                {analysis.avg_engagement_rate !== null && <> · {I.engagementRate(f.num(analysis.avg_engagement_rate))}</>}
              </p>
            </div>
          </Card>
          <Card>
            <CardHeader icon={<CalendarDays />} title={I.bestDays} />
            <div className="p-4 sm:p-5">
              <ColumnChart points={weekdays} caption={I.bestDays} format={compact} strong={new Set(analysis.best_days)} height={140} />
              {analysis.best_days.length > 0 && <p className="mt-2 text-sm font-medium text-ink-900">{analysis.best_days.map((d) => I.days[d]).join(" · ")}</p>}
            </div>
          </Card>
          <Card>
            <CardHeader icon={<CalendarClock />} title={I.bestHours} />
            <div className="p-4 sm:p-5">
              <ColumnChart points={hours} caption={I.bestHours} format={compact} strong={new Set(analysis.best_hours.map((h) => h / 3))} height={140} />
              <p className="mt-2 text-xs leading-5 text-slate-500">{I.bestTimesHint}</p>
            </div>
          </Card>
          <Card>
            <CardHeader icon={<Hash />} title={I.hashtags} />
            <div className="p-4 sm:p-5">
              {analysis.hashtags.length ? (
                <BarList rows={analysis.hashtags.map((h) => ({ key: h.tag, label: <span dir="auto">#{h.tag}</span>, value: h.avg_engagement }))} format={compact} />
              ) : (
                <p className="text-sm text-slate-500">{I.hashtagsEmpty}</p>
              )}
            </div>
          </Card>
        </div>
      </section>

      <Card>
        <CardHeader icon={<ThumbsUp />} title={I.topPosts} />
        <ul className="divide-y divide-slate-100">
          {analysis.top_posts.map((id) => media.get(id)).filter((m): m is InsightsMedia => !!m).map((m) => <TopPost key={m.id} media={m} />)}
        </ul>
      </Card>

      <Assistant report={data.report} />
    </div>
  );
}

function Kpi({ label, value, delta, note }: { label: string; value: string; delta?: number | null; note?: string }) {
  const { t } = useI18n();
  return (
    <Card className="p-4 sm:p-5">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink-950 sm:text-[1.75rem]">{value}</div>
      <div className="mt-1 min-h-5 text-xs text-slate-500">{note ?? <Delta value={delta} label={t.social.insights.vsLastWeek} />}</div>
    </Card>
  );
}

function TopPost({ media }: { media: InsightsMedia }) {
  const { t, f } = useI18n();
  const I = t.social.insights;
  const compact = useCompact();
  const stat = (value: number | null | undefined, label: string) =>
    value === null || value === undefined ? null : (
      <span>
        <span className="num font-medium text-ink-900">{compact(value)}</span> {label}
      </span>
    );
  return (
    <li className="flex gap-3 p-4 sm:px-5">
      <PostThumb src={media.preview_url} format={media.format} className="size-14" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="brand">{I.formats[media.format]}</Badge>
          {media.timestamp && <span className="text-xs text-slate-400">{f.date(media.timestamp)}</span>}
          {media.permalink && (
            <a href={media.permalink} target="_blank" rel="noopener noreferrer" className="ms-auto text-slate-400 hover:text-brand-700" aria-label={t.social.comments.openPost}>
              <ExternalLink className="size-4" />
            </a>
          )}
        </div>
        <p dir="auto" className="mt-1 line-clamp-2 text-sm leading-6 text-ink-800">
          {media.caption}
        </p>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
          {stat(media.reach, I.reachShort)}
          {stat(media.engagement, I.engagement)}
          {stat(media.saves, I.saves)}
          {stat(media.shares, I.shares)}
          {media.rate !== null && media.rate !== undefined && (
            <span>
              <span className="num font-medium text-ink-900">{f.num(media.rate)}%</span> {I.rate}
            </span>
          )}
        </div>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------- content assistant

function Assistant({ report }: { report: ContentReport | null | undefined }) {
  const { t, f } = useI18n();
  const A = t.social.assistant;
  const toast = useToast();
  const qc = useQueryClient();
  const analyze = useMutation({
    mutationFn: () => api<ContentReport>("/insights/report", { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.insights });
      qc.invalidateQueries({ queryKey: keys.dashboard });
      qc.invalidateQueries({ queryKey: keys.billing });
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  return (
    <section aria-labelledby="assistant-title" className="overflow-hidden rounded-xl border border-slate-200 bg-surface shadow-soft">
      <div className="flex flex-wrap items-center gap-4 border-b border-slate-200 bg-night-950 px-5 py-4 text-white sm:px-6">
        <span aria-hidden className="flex size-10 items-center justify-center rounded-lg bg-white/10 text-accent-300">
          <Wand2 className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 id="assistant-title" className="font-semibold tracking-tight">
            {A.title}
          </h2>
          <p className="text-sm leading-6 text-white/65">{A.subtitle}</p>
        </div>
        <div className="flex flex-col items-start gap-1 sm:items-end">
          <Button variant="inverse" size="sm" icon={<Sparkles className="size-4" />} loading={analyze.isPending} onClick={() => analyze.mutate()}>
            {analyze.isPending ? A.analyzing : report ? A.reanalyze : A.analyze}
          </Button>
          <span className="text-[11px] text-white/50">{A.charged}</span>
        </div>
      </div>

      {report && <Report report={report} dateLabel={A.reportFrom(f.dateTime(report.created_at))} />}
      <AssistantChat />
    </section>
  );
}

function Report({ report, dateLabel }: { report: ContentReport; dateLabel: string }) {
  const { t } = useI18n();
  const A = t.social.assistant;
  const I = t.social.insights;
  return (
    <div className="space-y-6 border-b border-slate-200 p-5 sm:p-6">
      <div>
        <p className="text-xs text-slate-500">{dateLabel}</p>
        <p dir="auto" className="mt-1 text-[15px] leading-7 text-ink-900">
          {report.summary}
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <ListBox title={A.strengths} items={report.strengths ?? []} tone="green" />
        <ListBox title={A.improvements} items={report.improvements ?? []} tone="amber" />
      </div>
      {!!report.recommendations?.length && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-ink-950">{A.recommendations}</h3>
          <ol className="space-y-2">
            {report.recommendations.map((r, i) => (
              <li key={i} className="flex gap-3 text-sm leading-6">
                <span className="num flex size-6 shrink-0 items-center justify-center rounded-full border border-brand-600 text-xs font-semibold text-brand-700">{i + 1}</span>
                <span dir="auto">
                  <span className="font-medium text-ink-950">{r.title}</span> <span className="text-slate-600">— {r.detail}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
      {!!report.ideas?.length && (
        <div>
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink-950">
            <Lightbulb className="size-4 text-accent-500" aria-hidden />
            {A.ideas}
          </h3>
          <div className="grid gap-3 md:grid-cols-2">
            {report.ideas.map((idea, i) => (
              <IdeaCard key={i} idea={idea} />
            ))}
          </div>
        </div>
      )}
      {!!report.weekly_plan?.length && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-ink-950">{A.plan}</h3>
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {report.weekly_plan.map((p, i) => (
              <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3.5 py-2.5 text-sm">
                <span className="w-24 shrink-0 font-medium text-ink-950" dir="auto">
                  {p.day}
                </span>
                <Badge tone="brand">{I.formats[p.format]}</Badge>
                <span dir="auto" className="min-w-0 flex-1 text-slate-600">
                  {p.idea}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ListBox({ title, items, tone }: { title: string; items: string[]; tone: "green" | "amber" }) {
  if (!items.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <h3 className="mb-2 text-sm font-semibold text-ink-950">{title}</h3>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} dir="auto" className="flex gap-2 text-sm leading-6 text-slate-700">
            <span aria-hidden className={cx("mt-2.5 size-1.5 shrink-0 rounded-full", tone === "green" ? "bg-emerald-500" : "bg-amber-500")} />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function IdeaCard({ idea }: { idea: ContentIdea }) {
  const { t } = useI18n();
  const A = t.social.assistant;
  const I = t.social.insights;
  const toast = useToast();
  const navigate = useNavigate();
  return (
    <div className="flex flex-col rounded-lg border border-slate-200 p-4">
      <div className="flex items-center gap-2">
        <Badge tone="brand">{I.formats[idea.format]}</Badge>
        {idea.when && <span className="text-xs text-slate-500">{idea.when}</span>}
      </div>
      <h4 dir="auto" className="mt-2 font-medium text-ink-950">
        {idea.title}
      </h4>
      <p dir="auto" className="mt-1 text-sm leading-6 text-slate-600">
        <span className="text-slate-400">{A.hook}: </span>
        {idea.hook}
      </p>
      <p dir="auto" className="user-text mt-2 flex-1 rounded-md bg-slate-50 px-3 py-2 text-sm leading-6 text-ink-800">
        {idea.caption}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="ghost"
          icon={<Copy className="size-4" />}
          onClick={() => {
            void navigator.clipboard?.writeText(idea.caption);
            toast.success(A.copied);
          }}
        >
          {A.copy}
        </Button>
        {idea.format === "story" && (
          <Button size="sm" variant="ghost" icon={<CalendarClock className="size-4" />} onClick={() => navigate("/stories", { state: { note: `${idea.title}: ${idea.hook}` } })}>
            {A.scheduleStory}
          </Button>
        )}
      </div>
    </div>
  );
}

type Turn = { role: "owner" | "assistant"; text: string };

function AssistantChat() {
  const { t } = useI18n();
  const A = t.social.assistant;
  const toast = useToast();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const ask = useMutation({
    mutationFn: (messages: Turn[]) => api<{ reply: string }>("/insights/assistant", { method: "POST", json: { messages } }),
    onSuccess: ({ reply }, messages) => {
      setTurns([...messages, { role: "assistant", text: reply }]);
      requestAnimationFrame(() => end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
    },
    onError: (err, messages) => {
      toast.error(errorMessage(err, t));
      setTurns(messages.slice(0, -1));
    },
  });

  const send = (text: string) => {
    const clean = text.trim();
    if (!clean || ask.isPending) return;
    const next: Turn[] = [...turns, { role: "owner", text: clean }];
    setTurns(next);
    setDraft("");
    ask.mutate(next.slice(-20));
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    send(draft);
  };

  return (
    <div className="p-5 sm:p-6">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-ink-950">{A.chatTitle}</h3>
        {turns.length > 0 && (
          <Button size="sm" variant="ghost" onClick={() => setTurns([])}>
            {A.clear}
          </Button>
        )}
      </div>
      {turns.length === 0 ? (
        <div className="flex flex-wrap gap-2">
          {A.suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => send(s)}
              className="rounded-md border border-slate-200 bg-surface px-3 py-1.5 text-start text-sm text-slate-600 transition-colors hover:border-brand-300 hover:text-brand-700"
            >
              {s}
            </button>
          ))}
        </div>
      ) : (
        <div className="max-h-[28rem] space-y-3 overflow-y-auto pe-1">
          {turns.map((turn, i) => (
            <Bubble key={i} mine={turn.role === "owner"}>
              {turn.text}
            </Bubble>
          ))}
          {ask.isPending && (
            <Bubble mine={false}>
              <span className="inline-flex items-center gap-1" aria-label={A.thinking}>
                <span className="typing-dot size-1.5 rounded-full bg-slate-400" />
                <span className="typing-dot size-1.5 rounded-full bg-slate-400 [animation-delay:0.2s]" />
                <span className="typing-dot size-1.5 rounded-full bg-slate-400 [animation-delay:0.4s]" />
              </span>
            </Bubble>
          )}
          <div ref={end} />
        </div>
      )}
      <form onSubmit={submit} className="mt-4 flex items-end gap-2">
        <Textarea
          rows={1}
          value={draft}
          maxLength={4000}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(draft);
            }
          }}
          placeholder={A.chatPlaceholder}
          className="max-h-40 min-h-11 resize-none"
        />
        <Button type="submit" icon={<Send className="size-4 rtl:-scale-x-100" />} disabled={!draft.trim() || ask.isPending} aria-label={A.send} className="h-11 shrink-0" />
      </form>
    </div>
  );
}

function Bubble({ mine, children }: { mine: boolean; children: ReactNode }) {
  return (
    <div className={cx("flex", mine ? "justify-end" : "justify-start")}>
      <div
        dir="auto"
        className={cx(
          "user-text max-w-[85%] rounded-lg px-3.5 py-2.5 text-sm leading-7",
          mine ? "rounded-se-sm bg-brand-600 text-white" : "rounded-ss-sm border border-slate-200 bg-slate-50 text-ink-900",
        )}
      >
        {children}
      </div>
    </div>
  );
}
