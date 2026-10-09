import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookPlus, HelpCircle, MessageSquare, Sparkles } from "lucide-react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Unanswered as Item } from "../api/types";
import { Avatar, MessageText } from "../components/conversation";
import FaqDialog from "../components/FaqDialog";
import { useToast } from "../components/toast";
import { Alert, Button, Card, EmptyState, LinkButton, PageHeader, PageLoading } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";

export default function Unanswered() {
  const { t, f } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const [adding, setAdding] = useState<Item | null>(null);

  const list = useQuery({ queryKey: keys.unanswered, queryFn: () => api<Item[]>("/unanswered", { query: { limit: 200 } }) });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.unanswered });
    qc.invalidateQueries({ queryKey: keys.dashboard });
    qc.invalidateQueries({ queryKey: keys.conversations });
  };

  const resolveReq = (messageId: string) => api(`/unanswered/${messageId}/resolve`, { method: "POST" });

  const ignore = useMutation({
    mutationFn: resolveReq,
    onSuccess: () => {
      toast.success(t.unanswered.ignored);
      refresh();
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  return (
    <div className="max-w-4xl">
      <PageHeader icon={<HelpCircle />} title={t.unanswered.title} subtitle={t.unanswered.subtitle} />

      {list.isPending ? (
        <PageLoading />
      ) : list.error ? (
        <Alert kind="error">{errorMessage(list.error, t)}</Alert>
      ) : list.data.length === 0 ? (
        <Card>
          <EmptyState icon={<Sparkles />} title={t.unanswered.empty} />
        </Card>
      ) : (
        <ul className="space-y-4">
          {list.data.map((item, i) => {
            const name = item.customer_username ?? t.common.customer;
            return (
              <li
                key={item.message_id}
                className="animate-pop-in overflow-hidden rounded-2xl bg-surface shadow-soft ring-1 ring-line transition-shadow duration-200 hover:shadow-lift"
                style={{ animationDelay: `${Math.min(i, 6) * 50}ms` }}
              >
                <div className="flex gap-3 px-5 pt-5 sm:px-6">
                  <Avatar name={name} className="size-9" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
                      <span dir="auto" className="font-semibold text-ink-950">
                        {name}
                      </span>
                      <span className="text-xs text-slate-400" title={f.dateTime(item.created_at)}>
                        {f.ago(item.created_at)}
                      </span>
                    </div>
                    <p className="user-text mt-2 w-fit max-w-full rounded-2xl rounded-ss-md bg-slate-100 px-4 py-2.5 text-sm leading-7 text-ink-900">
                      <MessageText text={item.question} />
                    </p>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 bg-slate-50/60 px-5 py-3 sm:px-6">
                  <Button size="sm" icon={<BookPlus className="size-4" />} onClick={() => setAdding(item)}>
                    {t.unanswered.add}
                  </Button>
                  <LinkButton to={`/inbox/${item.conversation_id}`} size="sm" variant="secondary" icon={<MessageSquare className="size-4" />}>
                    {t.common.viewConversation}
                  </LinkButton>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="sm:ms-auto"
                    loading={ignore.isPending && ignore.variables === item.message_id}
                    onClick={() => ignore.mutate(item.message_id)}
                  >
                    {t.unanswered.ignore}
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <FaqDialog
        question={adding?.question ?? null}
        onClose={() => setAdding(null)}
        onSaved={async () => {
          // saving the answer also closes the question
          if (adding) await resolveReq(adding.message_id);
          toast.success(t.unanswered.addedResolved);
          refresh();
        }}
      />
    </div>
  );
}
