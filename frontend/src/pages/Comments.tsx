import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Check,
  Eye,
  EyeOff,
  FlaskConical,
  Globe,
  Info,
  Lock,
  MessageCircleMore,
  RotateCcw,
  Send,
  Sparkles,
  X,
} from "lucide-react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Comment, CommentList, CommentMode, CommentTry, Shop } from "../api/types";
import { Avatar } from "../components/conversation";
import { InstagramNotice, PostThumb } from "../components/social";
import { useToast } from "../components/toast";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, Field, PageHeader, PageLoading, Tabs, Textarea, Toggle, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";

type View = "waiting" | "answered" | "skipped";
const WAITING_CATEGORIES = ["price", "availability", "product", "order", "complaint", "other", "none"] as const;

export default function Comments() {
  const { t, f } = useI18n();
  const C = t.social.comments;
  const [view, setView] = useState<View>("waiting");
  const [category, setCategory] = useState("");

  const list = useQuery({
    queryKey: keys.comments(view, category),
    queryFn: () => api<CommentList>("/comments", { query: { view, category: view === "waiting" ? category : "" } }),
    refetchInterval: 20_000,
  });
  const counts = list.data?.counts;

  return (
    <div className="max-w-6xl">
      <PageHeader icon={<MessageCircleMore />} title={C.title} subtitle={C.subtitle} />
      {list.data && <InstagramNotice connected={list.data.available || list.data.needs_reconnect} needsReconnect={list.data.needs_reconnect} />}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0">
          <Tabs<View>
            value={view}
            onChange={(v) => {
              setView(v);
              setCategory("");
            }}
            items={[
              { value: "waiting", label: C.tabs.waiting, count: counts ? f.num(counts.waiting) : undefined },
              { value: "answered", label: C.tabs.answered, count: counts ? f.num(counts.answered) : undefined },
              { value: "skipped", label: C.tabs.skipped, count: counts ? f.num(counts.skipped) : undefined },
            ]}
          />

          {view === "waiting" && counts && counts.waiting > 0 && (
            <div className="no-scrollbar -mx-4 mt-4 flex gap-2 overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0">
              <Chip active={category === ""} onClick={() => setCategory("")} label={C.allCategories} count={f.num(counts.waiting)} />
              {WAITING_CATEGORIES.filter((c) => counts.waiting_by_category[c]).map((c) => (
                <Chip key={c} active={category === c} onClick={() => setCategory(c)} label={C.categories[c]} count={f.num(counts.waiting_by_category[c] ?? 0)} />
              ))}
            </div>
          )}

          <div className="mt-5">
            {list.isPending ? (
              <PageLoading />
            ) : list.error ? (
              <Alert kind="error">{errorMessage(list.error, t)}</Alert>
            ) : list.data.items.length === 0 ? (
              <Card>
                <EmptyState icon={<Sparkles />} title={view === "waiting" ? C.emptyWaiting : view === "answered" ? C.emptyAnswered : C.emptySkipped}>
                  {view === "waiting" && C.emptyWaitingHint}
                </EmptyState>
              </Card>
            ) : (
              <ul className="space-y-4">
                {list.data.items.map((comment) => (
                  <CommentCard key={comment.id} comment={comment} />
                ))}
              </ul>
            )}
          </div>
        </div>

        <aside className="space-y-6 lg:sticky lg:top-6">
          <CommentSettings />
          <TryComment />
        </aside>
      </div>
    </div>
  );
}

function Chip({ active, onClick, label, count }: { active: boolean; onClick: () => void; label: string; count: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cx(
        "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border px-2.5 text-sm transition-colors",
        active ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-200 bg-surface text-slate-600 hover:border-slate-300 hover:text-ink-900",
      )}
    >
      {label}
      <span className="num text-xs text-slate-500">{count}</span>
    </button>
  );
}

function useRefreshComments() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["comments"] });
    qc.invalidateQueries({ queryKey: keys.dashboard });
  };
}

function CommentCard({ comment }: { comment: Comment }) {
  const { t, f } = useI18n();
  const C = t.social.comments;
  const toast = useToast();
  const refresh = useRefreshComments();
  const [composer, setComposer] = useState<"public" | "private" | null>(null);
  const [text, setText] = useState("");
  const waiting = comment.status === "unanswered" || comment.status === "pending";
  const kind = comment.post_kind === "reel" ? C.onReel : comment.post_kind === "ad" ? C.onAd : C.onPost;

  const act = useMutation({
    mutationFn: ({ path, json }: { path: string; json?: unknown; done: string }) =>
      api<Comment>(`/comments/${comment.id}/${path}`, { method: "POST", json }),
    onSuccess: (_, vars) => {
      toast.success(vars.done);
      setComposer(null);
      setText("");
      refresh();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  const send = (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim() || !composer) return;
    act.mutate({ path: "reply", json: { text: text.trim(), private: composer === "private" }, done: C.sent });
  };

  return (
    <li className="overflow-hidden rounded-xl border border-slate-200 bg-surface shadow-soft">
      <div className="flex gap-3 p-4 sm:p-5">
        <Avatar name={comment.author_username || "?"} className="size-9 text-sm" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
            <span className="ltr font-semibold text-ink-950">@{comment.author_username}</span>
            <span className="text-xs text-slate-400" title={f.dateTime(comment.commented_at)}>
              {f.ago(comment.commented_at)} · {kind}
            </span>
            {comment.is_reply && <span className="text-xs text-slate-400">· {C.isReply}</span>}
            <span className="ms-auto flex items-center gap-1.5">
              {comment.hidden && (
                <Badge>
                  <EyeOff />
                  {C.hidden}
                </Badge>
              )}
              {comment.category && <Badge tone={comment.category === "complaint" ? "red" : comment.category === "spam" ? "neutral" : "brand"}>{C.categories[comment.category]}</Badge>}
            </span>
          </div>
          <p dir="auto" className="user-text mt-2 w-fit max-w-full rounded-lg rounded-ss-sm bg-slate-100 px-3.5 py-2 text-sm leading-6 text-ink-900">
            {comment.text}
          </p>

          {(comment.post_caption || comment.post_permalink) && (
            <a
              href={comment.post_permalink ?? undefined}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 flex max-w-md items-center gap-2.5 rounded-lg border border-slate-200 p-2 text-xs text-slate-500 transition-colors hover:border-slate-300 hover:text-ink-800"
            >
              <PostThumb src={comment.post_preview_url} format={comment.post_kind} className="size-9" />
              <span dir="auto" className="line-clamp-2 min-w-0 flex-1 leading-5">
                {comment.post_caption || C.openPost}
              </span>
            </a>
          )}

          {(comment.public_reply || comment.private_reply) && (
            <div className="mt-3 space-y-2">
              {comment.private_reply && <Reply icon={<Lock />} label={C.privateReply} text={comment.private_reply} bot={comment.status === "answered"} />}
              {comment.public_reply && <Reply icon={<Globe />} label={C.publicReply} text={comment.public_reply} bot={comment.status === "answered"} />}
            </div>
          )}

          {waiting && comment.reason && (
            <p className="mt-3 flex items-start gap-2 text-sm leading-6 text-slate-600">
              <Info className="mt-1 size-4 shrink-0 text-amber-500" aria-hidden />
              <span>
                <span className="text-slate-500">{C.whyWaiting}: </span>
                <bdi>{comment.reason}</bdi>
              </span>
            </p>
          )}
          {comment.status === "pending" && (
            <p className="mt-3 flex items-center gap-2 text-sm text-slate-500">
              <Bot className="size-4 text-brand-500" aria-hidden />
              {C.status.pending}
            </p>
          )}
          {comment.error && !waiting && <p className="mt-2 text-xs text-amber-700">{comment.error}</p>}
        </div>
      </div>

      {composer && (
        <form onSubmit={send} className="border-t border-slate-100 bg-slate-50 px-4 py-3 sm:px-5">
          <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-slate-600">
            {composer === "private" ? <Lock className="size-3.5" /> : <Globe className="size-3.5" />}
            {composer === "private" ? C.replyPrivate : C.replyPublic}
          </div>
          <Textarea data-autofocus autoFocus rows={2} value={text} maxLength={900} onChange={(e) => setText(e.target.value)} placeholder={C.replyPlaceholder} />
          {composer === "private" && <p className="mt-1.5 text-xs text-slate-500">{C.onePrivate}</p>}
          <div className="mt-2 flex gap-2">
            <Button type="submit" size="sm" icon={<Send className="size-4 rtl:-scale-x-100" />} loading={act.isPending} disabled={!text.trim()}>
              {C.send}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setComposer(null)}>
              {t.common.cancel}
            </Button>
          </div>
        </form>
      )}

      {!composer && (
        <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 px-4 py-2.5 sm:px-5">
          {waiting && comment.status !== "pending" && (
            <>
              <Button size="sm" variant="secondary" icon={<Globe className="size-4" />} onClick={() => setComposer("public")}>
                {C.replyPublic}
              </Button>
              {!comment.private_reply_sent && (
                <Button size="sm" variant="secondary" icon={<Lock className="size-4" />} onClick={() => setComposer("private")}>
                  {C.replyPrivate}
                </Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                icon={<RotateCcw className="size-4" />}
                title={C.retryHint}
                loading={act.isPending && act.variables?.path === "retry"}
                onClick={() => act.mutate({ path: "retry", done: C.retried })}
              >
                {C.retry}
              </Button>
              <Button size="sm" variant="ghost" icon={<X className="size-4" />} onClick={() => act.mutate({ path: "dismiss", done: C.dismissed })}>
                {C.dismiss}
              </Button>
            </>
          )}
          {!waiting && (
            <span className="flex items-center gap-1.5 text-xs text-slate-500">
              {comment.status === "answered" || comment.status === "owner_replied" ? <Check className="size-3.5 text-emerald-600" /> : null}
              {C.status[comment.status]}
              {comment.handled_at && <> · {f.ago(comment.handled_at)}</>}
            </span>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="ms-auto"
            icon={comment.hidden ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
            onClick={() => act.mutate({ path: "hide", json: { hidden: !comment.hidden }, done: comment.hidden ? C.shownDone : C.hiddenDone })}
          >
            {comment.hidden ? C.unhide : C.hide}
          </Button>
        </div>
      )}
    </li>
  );
}

function Reply({ icon, label, text, bot }: { icon: React.ReactNode; label: string; text: string; bot: boolean }) {
  return (
    <div className="rounded-lg border border-brand-200 bg-brand-50/60 px-3.5 py-2.5">
      <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium text-brand-700 [&>svg]:size-3.5">
        {bot ? <Bot /> : icon}
        {label}
      </div>
      <p dir="auto" className="user-text text-sm leading-6 text-ink-900">
        {text}
      </p>
    </div>
  );
}

const MODES: CommentMode[] = ["both", "private", "public", "off"];

function CommentSettings() {
  const { t } = useI18n();
  const C = t.social.comments;
  const toast = useToast();
  const qc = useQueryClient();
  const shop = useQuery({ queryKey: keys.shop, queryFn: () => api<Shop>("/shop") });
  const save = useMutation({
    mutationFn: (json: Partial<Pick<Shop, "comment_mode" | "comment_thank_praise" | "comment_hide_spam">>) => api<Shop>("/shop", { method: "PATCH", json }),
    onSuccess: (data) => {
      qc.setQueryData(keys.shop, data);
      qc.invalidateQueries({ queryKey: keys.me });
      toast.success(t.common.saved);
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });
  const s = shop.data;

  return (
    <Card>
      <CardHeader title={C.settingsTitle} />
      {!s ? (
        <PageLoading />
      ) : (
        <div className="space-y-4 p-4 sm:p-5">
          <div role="radiogroup" aria-label={C.settingsTitle} className="space-y-2">
            {MODES.map((mode) => {
              const on = s.comment_mode === mode;
              return (
                <button
                  key={mode}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  disabled={save.isPending}
                  onClick={() => !on && save.mutate({ comment_mode: mode })}
                  className={cx(
                    "flex w-full items-start gap-3 rounded-lg border px-3 py-2.5 text-start transition-colors",
                    on ? "border-brand-600 bg-brand-50/70" : "border-slate-200 hover:border-slate-300",
                  )}
                >
                  <span aria-hidden className={cx("mt-1 flex size-4 shrink-0 items-center justify-center rounded-full border", on ? "border-brand-600" : "border-slate-300")}>
                    {on && <span className="size-2 rounded-full bg-brand-600" />}
                  </span>
                  <span className="min-w-0">
                    <span className="flex items-center gap-2 text-sm font-medium text-ink-950">
                      {C.modes[mode].title}
                      {mode === "both" && <Badge tone="brand">{C.recommended}</Badge>}
                    </span>
                    <span className="mt-0.5 block text-xs leading-5 text-slate-500">{C.modes[mode].body}</span>
                  </span>
                </button>
              );
            })}
          </div>
          <div className="space-y-3 border-t border-slate-100 pt-4">
            <SettingToggle
              label={C.thankPraise}
              hint={C.thankPraiseHint}
              checked={s.comment_thank_praise}
              disabled={save.isPending || s.comment_mode === "off"}
              onChange={(v) => save.mutate({ comment_thank_praise: v })}
            />
            <SettingToggle
              label={C.hideSpam}
              hint={C.hideSpamHint}
              checked={s.comment_hide_spam}
              disabled={save.isPending || s.comment_mode === "off"}
              onChange={(v) => save.mutate({ comment_hide_spam: v })}
            />
          </div>
        </div>
      )}
    </Card>
  );
}

function SettingToggle({ label, hint, checked, disabled, onChange }: { label: string; hint: string; checked: boolean; disabled?: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="text-sm font-medium text-ink-900">{label}</div>
        <div className="mt-0.5 text-xs leading-5 text-slate-500">{hint}</div>
      </div>
      <Toggle checked={checked} onChange={onChange} disabled={disabled} label={label} />
    </div>
  );
}

function TryComment() {
  const { t } = useI18n();
  const C = t.social.comments;
  const toast = useToast();
  const [text, setText] = useState("");
  const [caption, setCaption] = useState("");
  const [result, setResult] = useState<CommentTry | null>(null);
  const run = useMutation({
    mutationFn: () => api<CommentTry>("/comments/try", { method: "POST", json: { text: text.trim(), post_caption: caption.trim() } }),
    onSuccess: setResult,
    onError: (err) => toast.error(errorMessage(err, t)),
  });
  useEffect(() => setResult(null), [text, caption]);

  return (
    <Card>
      <CardHeader icon={<FlaskConical />} title={C.tryTitle} />
      <form
        className="space-y-3 p-4 sm:p-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) run.mutate();
        }}
      >
        <p className="text-xs leading-5 text-slate-500">{C.tryHint}</p>
        <Field label={C.tryComment}>
          {(id) => <Textarea id={id} rows={2} value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} placeholder={C.tryCommentPlaceholder} />}
        </Field>
        <Field label={C.tryCaption}>
          {(id) => <Textarea id={id} rows={2} value={caption} maxLength={2200} onChange={(e) => setCaption(e.target.value)} placeholder={C.tryCaptionPlaceholder} />}
        </Field>
        <Button type="submit" className="w-full" loading={run.isPending} disabled={!text.trim()}>
          {C.tryRun}
        </Button>
        {result && (
          <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
            {!result.ai_ready && <Alert kind="info">{C.tryNoAi}</Alert>}
            <div className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink-950">
              {result.decision === "answer" ? <Check className="size-4 text-emerald-600" /> : <Info className="size-4 text-amber-500" />}
              {C.tryDecision[result.decision]}
              <Badge tone="brand">{C.categories[result.category]}</Badge>
            </div>
            {result.reason && <p className="text-xs leading-5 text-slate-600">{result.reason}</p>}
            {result.private_reply && <Reply icon={<Lock />} label={C.privateReply} text={result.private_reply} bot />}
            {result.public_reply && <Reply icon={<Globe />} label={C.publicReply} text={result.public_reply} bot />}
          </div>
        )}
      </form>
    </Card>
  );
}
