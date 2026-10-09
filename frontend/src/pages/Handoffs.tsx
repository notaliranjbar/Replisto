import { useEffect, useState } from "react";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, BellOff, BellRing, Bot, BookPlus, CheckCheck, Clock, ExternalLink, Info, MessageSquare, PartyPopper } from "lucide-react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { HandoffItem, HandoffPage } from "../api/types";
import { ChannelIcon, useChannelLabel } from "../components/channel";
import { Avatar, MessageText, useCustomerName } from "../components/conversation";
import FaqDialog from "../components/FaqDialog";
import { useToast } from "../components/toast";
import { Alert, Badge, Button, Card, EmptyState, ExternalButton, LinkButton, PageHeader, PageLoading, Tabs, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";
import { useNotificationPermission } from "../lib/notifications";

type Status = "open" | "resolved";
const PAGE = 30;
const HOUR = 3600_000;

export default function Handoffs() {
  const { t, f } = useI18n();
  const [status, setStatus] = useState<Status>("open");
  const [faq, setFaq] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  // keep "waiting for 14 minutes" fresh
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  const list = useInfiniteQuery({
    queryKey: [...keys.handoffs, status],
    queryFn: ({ pageParam }) => api<HandoffPage>("/handoffs", { query: { status, offset: pageParam, limit: PAGE } }),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((n, p) => n + p.items.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
    refetchInterval: 20_000,
  });
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  const total = list.data?.pages[0]?.total;

  return (
    <div className="max-w-4xl">
      <PageHeader icon={<BellRing />} title={t.handoffs.title} subtitle={t.handoffs.subtitle} action={<NotificationButton />} />

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <Tabs
          value={status}
          onChange={setStatus}
          items={[
            { value: "open", label: t.handoffs.tabOpen, count: status === "open" && total ? f.num(total) : undefined },
            { value: "resolved", label: t.handoffs.tabResolved },
          ]}
        />
        {status === "open" && items.length > 0 && (
          <p className="flex items-center gap-1.5 text-sm text-slate-500">
            <Info className="size-4 shrink-0 text-brand-500" aria-hidden />
            {t.handoffs.autoCloseNote}
          </p>
        )}
      </div>

      {list.isPending ? (
        <PageLoading />
      ) : list.error ? (
        <Alert kind="error">{errorMessage(list.error, t)}</Alert>
      ) : items.length === 0 ? (
        <Card>
          {status === "open" ? (
            <EmptyState icon={<PartyPopper />} title={t.handoffs.emptyOpen} />
          ) : (
            <EmptyState icon={<CheckCheck />} title={t.handoffs.emptyResolved} />
          )}
        </Card>
      ) : (
        <div className="space-y-4">
          {items.map((item, i) => (
            <HandoffCard key={item.conversation_id} item={item} now={now} index={i} onAddFaq={() => setFaq(item.handoff.question)} />
          ))}
          {list.hasNextPage && (
            <div className="pt-2 text-center">
              <Button variant="secondary" size="sm" loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>
                {t.common.loadMore}
              </Button>
            </div>
          )}
        </div>
      )}

      <FaqDialog question={faq} onClose={() => setFaq(null)} />
    </div>
  );
}

/** One waiting customer: who, how long, what they asked, why the bot handed over, what to do. */
function HandoffCard({ item, now, index, onAddFaq }: { item: HandoffItem; now: number; index: number; onAddFaq: () => void }) {
  const { t, f } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const name = useCustomerName()(item.customer_username, item.customer_igsid, item.customer_name);
  const channelLabel = useChannelLabel()(item.channel);
  const h = item.handoff;
  const open = h.status === "open";
  const late = open && now - new Date(h.handed_off_at).getTime() > HOUR;

  const resolve = useMutation({
    mutationFn: () => api(`/handoffs/${item.conversation_id}/resolve`, { method: "POST" }),
    onSuccess: () => {
      toast.success(t.handoffs.resolved);
      qc.invalidateQueries({ queryKey: keys.handoffs });
      qc.invalidateQueries({ queryKey: keys.dashboard });
      qc.invalidateQueries({ queryKey: keys.conversations });
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  return (
    <article
      className={cx(
        "animate-pop-in overflow-hidden rounded-2xl bg-surface shadow-soft ring-1 transition-shadow duration-200 hover:shadow-lift",
        late ? "ring-amber-300" : "ring-line",
      )}
      style={{ animationDelay: `${Math.min(index, 6) * 50}ms` }}
    >
      <div className="flex flex-wrap items-center gap-3 px-5 pt-5 sm:px-6">
        <Avatar name={name} />
        <div className="min-w-0 flex-1">
          <span dir="auto" className="font-semibold text-ink-950">
            {name}
          </span>
          <div className="mt-0.5 flex items-center gap-1.5 text-xs text-slate-500">
            <ChannelIcon channel={item.channel} />
            {channelLabel}
          </div>
          {!open && h.resolved_at && <div className="text-xs text-slate-400">{f.smart(h.resolved_at)}</div>}
        </div>
        {open ? (
          <Badge tone={late ? "amber" : "red"}>
            <Clock aria-hidden />
            {t.handoffs.waitingFor(f.duration(h.handed_off_at, now))}
          </Badge>
        ) : (
          <Badge tone="green">
            <CheckCheck aria-hidden />
            {h.resolved_by === "owner_reply" ? t.handoffs.resolvedByOwner : t.handoffs.resolvedManual}
          </Badge>
        )}
      </div>

      <div className="px-5 py-4 sm:px-6">
        <div className="mb-1.5 text-xs font-semibold text-slate-500">{t.handoffs.question}</div>
        <p className="user-text w-fit max-w-full rounded-2xl rounded-ss-md bg-slate-100 px-4 py-2.5 text-sm leading-7 text-ink-900">
          <MessageText text={h.question} />
        </p>
        {h.reason && (
          <p className="mt-3 flex items-start gap-2 text-sm leading-6 text-slate-600">
            <Bot className="mt-0.5 size-4 shrink-0 text-brand-500" aria-hidden />
            <span>
              <span className="font-semibold text-ink-800">{t.handoffs.reason}: </span>
              {h.reason}
            </span>
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 bg-slate-50/60 px-5 py-3 sm:px-6">
        <LinkButton to={`/inbox/${item.conversation_id}`} size="sm" variant={open ? "primary" : "secondary"} icon={<MessageSquare className="size-4" />}>
          {open ? t.launch.composer.send : t.common.viewConversation}
        </LinkButton>
        {open && item.chat_url && (
          <ExternalButton href={item.chat_url} size="sm" variant="secondary" icon={<ExternalLink className="size-4" />}>
            {t.launch.channel.openIn(channelLabel)}
          </ExternalButton>
        )}
        {open && (
          <Button size="sm" variant="secondary" loading={resolve.isPending} onClick={() => resolve.mutate()} title={t.handoffs.resolveHint}>
            {t.handoffs.resolve}
          </Button>
        )}
        <Button size="sm" variant="ghost" icon={<BookPlus className="size-4" />} onClick={onAddFaq} className="sm:ms-auto">
          {t.common.addToKnowledge}
        </Button>
      </div>
    </article>
  );
}

function NotificationButton() {
  const { t } = useI18n();
  const { permission, request } = useNotificationPermission();
  if (permission === "unsupported") return null;
  if (permission === "granted")
    return (
      <Badge tone="green" className="py-1.5">
        <Bell aria-hidden />
        {t.handoffs.notificationsOn}
      </Badge>
    );
  if (permission === "denied")
    return (
      <Badge className="py-1.5">
        <BellOff aria-hidden />
        {t.handoffs.notificationsBlocked}
      </Badge>
    );
  return (
    <Button variant="soft" size="md" icon={<Bell className="size-4" />} onClick={request}>
      {t.handoffs.enableNotifications}
    </Button>
  );
}
