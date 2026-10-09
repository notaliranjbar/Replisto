import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BellRing, ExternalLink, Inbox as InboxIcon, MessageSquare, Pause, Play, Search, SendHorizontal } from "lucide-react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Conversation, ConversationDetail, ConversationFilter, ConversationPage } from "../api/types";
import { ChannelIcon, useChannelLabel } from "../components/channel";
import { Avatar, MessageBubble, isIndefinitePause, useCustomerName, useMessagePreview } from "../components/conversation";
import { useToast } from "../components/toast";
import { Alert, Button, EmptyState, ExternalButton, Input, PageLoading, Spinner, Tabs, Textarea, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";

const PAGE = 30;
// No WebSocket: poll while the tab is visible (TanStack pauses intervals in background tabs).
const POLL_MS = 12_000;

/**
 * Two panes: the conversation list and the open thread. Phones show one pane at a time and
 * fill the screen between the top bar and the tab bar; desktop gets a contained card.
 */
export default function Inbox() {
  const { id } = useParams();
  return (
    <div
      className={cx(
        "-mx-4 -my-6 flex h-[calc(100dvh-var(--chrome-top)-var(--chrome-bottom))] bg-surface sm:-mx-6",
        "lg:m-0 lg:h-[calc(100dvh-5rem)] lg:overflow-hidden lg:rounded-2xl lg:shadow-soft lg:ring-1 lg:ring-line",
      )}
    >
      <div className={cx("w-full shrink-0 flex-col border-e border-slate-100 lg:flex lg:w-[24rem]", id ? "hidden" : "flex")}>
        <ConversationList selected={id} />
      </div>
      <div className={cx("min-w-0 flex-1 flex-col bg-canvas", id ? "flex" : "hidden lg:flex")}>
        {id ? (
          <ConversationView key={id} id={id} />
        ) : (
          <div className="m-auto">
            <EmptyState icon={<MessageSquare />} title={<SelectPrompt />} />
          </div>
        )}
      </div>
    </div>
  );
}

function SelectPrompt() {
  const { t } = useI18n();
  return <>{t.inbox.selectConversation}</>;
}

function ConversationList({ selected }: { selected?: string }) {
  const { t } = useI18n();
  const [filter, setFilter] = useState<ConversationFilter>("all");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    const id = setTimeout(() => setSearch(q.trim()), 300);
    return () => clearTimeout(id);
  }, [q]);

  const list = useInfiniteQuery({
    queryKey: [...keys.conversations, filter, search],
    queryFn: ({ pageParam }) => api<ConversationPage>("/conversations", { query: { filter, q: search, offset: pageParam, limit: PAGE } }),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((n, p) => n + p.items.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
    refetchInterval: POLL_MS,
  });

  const items = list.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <>
      <div className="space-y-3 border-b border-slate-100 p-4">
        <div className="flex items-center gap-2.5">
          <span aria-hidden className="flex size-9 items-center justify-center rounded-xl bg-brand-600 text-white shadow-md shadow-brand-600/25">
            <InboxIcon className="size-[18px]" />
          </span>
          <h1 className="text-lg font-semibold tracking-tight text-ink-950">{t.inbox.title}</h1>
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute start-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
          <Input
            className="ps-10"
            placeholder={t.inbox.searchPlaceholder}
            aria-label={t.inbox.searchPlaceholder}
            value={q}
            maxLength={64}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <Tabs
          compact
          value={filter}
          onChange={setFilter}
          items={[
            { value: "all", label: t.inbox.filterAll },
            { value: "needs_owner", label: t.inbox.filterNeedsOwner },
            { value: "unanswered", label: t.inbox.filterUnanswered },
            { value: "paused", label: t.inbox.filterPaused },
          ]}
        />
      </div>
      <div className="flex-1 overflow-y-auto">
        {list.isPending ? (
          <PageLoading />
        ) : list.error ? (
          <div className="p-4">
            <Alert kind="error">{errorMessage(list.error, t)}</Alert>
          </div>
        ) : items.length === 0 ? (
          <EmptyState icon={<InboxIcon />} title={t.inbox.empty} />
        ) : (
          <ul className="p-2">
            {items.map((c) => (
              <ConversationRow key={c.id} c={c} active={c.id === selected} />
            ))}
          </ul>
        )}
        {list.hasNextPage && (
          <div className="p-3 text-center">
            <Button size="sm" variant="ghost" loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>
              {t.common.loadMore}
            </Button>
          </div>
        )}
      </div>
    </>
  );
}

function ConversationRow({ c, active }: { c: Conversation; active: boolean }) {
  const { t, f } = useI18n();
  const name = useCustomerName()(c.customer_username, c.customer_id, c.customer_name);
  const preview = useMessagePreview();
  const waiting = c.handoff?.status === "open";
  const time = c.last_message?.created_at ?? c.last_customer_message_at;

  return (
    <li>
      <Link
        to={`/inbox/${c.id}`}
        aria-current={active ? "page" : undefined}
        className={cx("flex gap-3 rounded-xl px-3 py-3 transition-colors", active ? "bg-brand-50" : "hover:bg-slate-50")}
      >
        <span className="relative">
          <Avatar name={name} solid={active} />
          {waiting && <span className="absolute -end-0.5 -top-0.5 size-3 rounded-full bg-red-500 ring-2 ring-surface" />}
          <span className="absolute -bottom-0.5 -start-0.5 flex size-4 items-center justify-center rounded-full bg-surface ring-1 ring-line">
            <ChannelIcon channel={c.channel} className="size-2.5" />
          </span>
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span dir="auto" className={cx("truncate text-sm font-semibold", active ? "text-brand-800" : "text-ink-950")}>
              {name}
            </span>
            {time && <span className="ms-auto shrink-0 text-[11px] text-slate-400">{f.smart(time)}</span>}
          </div>
          {c.last_message && (
            <p className="mt-0.5 truncate text-[13px] text-slate-500">
              {c.last_message.sender === "bot" && <span className="font-medium text-brand-700">{t.inbox.senderBot}: </span>}
              {c.last_message.sender === "owner" && <span className="font-medium text-ink-800">{t.inbox.senderOwner}: </span>}
              {preview(c.last_message.text)}
            </p>
          )}
          {(waiting || c.bot_paused || c.open_unanswered > 0) && (
            <div className="mt-1.5 flex flex-wrap gap-1 text-[11px] font-semibold">
              {waiting && <span className="rounded-full bg-red-50 px-2 py-0.5 text-red-700">{t.inbox.badgeWaiting}</span>}
              {c.bot_paused && <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-800">{t.inbox.badgePaused}</span>}
              {c.open_unanswered > 0 && !waiting && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">{t.inbox.botDidntKnow}</span>}
            </div>
          )}
        </div>
      </Link>
    </li>
  );
}

function ConversationView({ id }: { id: string }) {
  const { t, f } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const name = useCustomerName();
  const channelLabel = useChannelLabel();
  const bottom = useRef<HTMLDivElement>(null);
  const [pauseMenu, setPauseMenu] = useState(false);

  const detail = useQuery({
    queryKey: keys.conversation(id),
    queryFn: () => api<ConversationDetail>(`/conversations/${id}`),
    refetchInterval: POLL_MS,
  });

  const messageCount = detail.data?.messages.length ?? 0;
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messageCount]);

  // Only messages that arrive while the conversation is open animate in, not the history.
  const initialIds = useRef<Set<string> | null>(null);
  if (detail.data && !initialIds.current) initialIds.current = new Set(detail.data.messages.map((m) => m.id));

  const onUpdated = (c: Conversation) => {
    qc.setQueryData<ConversationDetail>(keys.conversation(id), (old) => (old ? { ...old, ...c } : old));
    qc.invalidateQueries({ queryKey: keys.conversations });
  };

  const pause = useMutation({
    mutationFn: (minutes: number | null) => api<Conversation>(`/conversations/${id}/pause`, { method: "POST", json: minutes ? { minutes } : {} }),
    onSuccess: (c) => {
      setPauseMenu(false);
      onUpdated(c);
      toast.success(t.inbox.paused);
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  const resume = useMutation({
    mutationFn: () => api<Conversation>(`/conversations/${id}/resume`, { method: "POST" }),
    onSuccess: (c) => {
      onUpdated(c);
      toast.success(t.inbox.resumed);
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  if (detail.isPending)
    return (
      <div className="flex flex-1 items-center justify-center">
        <Spinner className="size-7" />
      </div>
    );
  if (detail.error)
    return (
      <div className="p-6">
        <Alert kind="error">{errorMessage(detail.error, t)}</Alert>
      </div>
    );

  const c = detail.data;
  const display = name(c.customer_username, c.customer_id, c.customer_name);
  const waiting = c.handoff?.status === "open";

  return (
    <>
      <header className="flex items-center gap-3 border-b border-slate-100 bg-surface px-3 py-3 sm:px-5">
        <button
          type="button"
          onClick={() => navigate("/inbox")}
          className="inline-flex size-10 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-ink-950 lg:hidden"
          aria-label={t.inbox.backToList}
        >
          <ArrowRight className="size-5 ltr:rotate-180" aria-hidden />
        </button>
        <Avatar name={display} />
        <div className="min-w-0 flex-1">
          <div className="truncate font-semibold text-ink-950">
            <span dir="auto">{display}</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <ChannelIcon channel={c.channel} />
            {channelLabel(c.channel)}
            {c.customer_username && (
              <a
                href={`https://instagram.com/${c.customer_username}`}
                target="_blank"
                rel="noopener noreferrer"
                dir="ltr"
                className="font-medium text-brand-700 hover:underline"
              >
                @{c.customer_username}
              </a>
            )}
          </div>
        </div>
        {c.bot_paused ? (
          <Button size="sm" variant="secondary" icon={<Play className="size-4" />} loading={resume.isPending} onClick={() => resume.mutate()} title={t.inbox.resume}>
            <span className="max-sm:sr-only">{t.inbox.resume}</span>
          </Button>
        ) : (
          <div className="relative">
            <Button
              size="sm"
              variant="secondary"
              icon={<Pause className="size-4" />}
              onClick={() => setPauseMenu(!pauseMenu)}
              loading={pause.isPending}
              aria-expanded={pauseMenu}
              aria-haspopup="menu"
              title={t.inbox.pause}
            >
              <span className="max-sm:sr-only">{t.inbox.pause}</span>
            </Button>
            {pauseMenu && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setPauseMenu(false)} />
                <div role="menu" className="animate-pop-in absolute end-0 z-20 mt-2 w-56 overflow-hidden rounded-xl bg-surface p-1.5 shadow-lift ring-1 ring-line">
                  {[
                    [120, t.inbox.pause2h],
                    [1440, t.inbox.pause24h],
                    [null, t.inbox.pauseForever],
                  ].map(([mins, label]) => (
                    <button
                      key={String(mins)}
                      type="button"
                      role="menuitem"
                      onClick={() => pause.mutate(mins as number | null)}
                      className="block w-full rounded-lg px-3 py-2.5 text-start text-sm font-medium text-ink-900 transition-colors hover:bg-brand-50 hover:text-brand-700"
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </header>

      {(waiting || c.bot_paused) && (
        <div className="space-y-px">
          {waiting && c.handoff && (
            <div className="flex items-start gap-2.5 bg-red-50 px-4 py-2.5 text-sm text-red-800 sm:px-5">
              <BellRing className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>
                <b>{t.inbox.badgeWaiting}</b>
                {c.handoff.reason && (
                  <>
                    {" · "}
                    {t.inbox.handoffReason}: {c.handoff.reason}
                  </>
                )}
              </span>
            </div>
          )}
          {c.bot_paused && (
            <div className="flex items-start gap-2.5 bg-amber-50 px-4 py-2.5 text-sm text-amber-900 sm:px-5">
              <Pause className="mt-0.5 size-4 shrink-0" aria-hidden />
              {isIndefinitePause(c.bot_paused_until) ? t.inbox.pausedIndefinitely : t.inbox.pausedUntil(f.smart(c.bot_paused_until!))}
            </div>
          )}
        </div>
      )}

      <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
        {c.messages.map((m) => (
          <MessageBubble key={m.id} message={m} animate={!initialIds.current?.has(m.id)} />
        ))}
        <div ref={bottom} />
      </div>

      <Composer conversation={c} onSent={onUpdated} openLabel={t.launch.channel.openIn(channelLabel(c.channel))} />
    </>
  );
}

/** The owner's own reply, sent on the conversation's channel (the bot then steps back). */
function Composer({ conversation, onSent, openLabel }: { conversation: Conversation; onSent: (c: Conversation) => void; openLabel: string }) {
  const { t } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const send = useMutation({
    mutationFn: () => api<Conversation>(`/conversations/${conversation.id}/reply`, { method: "POST", json: { text: text.trim() } }),
    onSuccess: (c) => {
      setText("");
      onSent(c);
      qc.invalidateQueries({ queryKey: keys.conversation(conversation.id) });
      qc.invalidateQueries({ queryKey: keys.handoffs });
      qc.invalidateQueries({ queryKey: keys.dashboard });
      toast.success(t.launch.composer.sent);
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });
  return (
    <footer className="border-t border-slate-100 bg-surface px-3 py-3 sm:px-5">
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) send.mutate();
        }}
      >
        <Textarea
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              if (text.trim()) send.mutate();
            }
          }}
          placeholder={t.launch.composer.placeholder}
          aria-label={t.launch.composer.placeholder}
          className="max-h-40 min-h-11 flex-1 resize-none"
          maxLength={4000}
        />
        <Button type="submit" loading={send.isPending} disabled={!text.trim()} icon={<SendHorizontal className="size-4 rtl:-scale-x-100" />} aria-label={t.launch.composer.send}>
          <span className="max-sm:sr-only">{t.launch.composer.send}</span>
        </Button>
      </form>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <p className="min-w-0 flex-1 text-xs leading-5 text-slate-500">{t.launch.composer.hint}</p>
        {conversation.chat_url && (
          <ExternalButton href={conversation.chat_url} size="sm" variant="ghost" icon={<ExternalLink className="size-4" />}>
            {openLabel}
          </ExternalButton>
        )}
      </div>
    </footer>
  );
}
