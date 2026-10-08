// "Ask Replisto": our own assistant, the same bot shops get, answering questions about Replisto.
// Used on the public site (inline) and in the panel (a floating launcher). A ring shows how
// much of today's chat allowance is left; guests are invited to sign up for more.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageCircleQuestion, Send, Sparkles, UsersRound, X } from "lucide-react";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";
import { LogoMark } from "./Logo";
import { MessageText } from "./conversation";
import { Alert, Button, buttonClass, cx } from "./ui";

type SiteChat = components["schemas"]["SiteChatOut"];
type Quota = components["schemas"]["QuotaOut"];

const VISITOR_KEY = "replisto.visitor";
let memoryVisitor: string | null = null;

/** A random id this browser keeps, so a guest's chat survives reloads. */
function visitorId(): string {
  try {
    const saved = localStorage.getItem(VISITOR_KEY);
    if (saved) return saved;
    const fresh = crypto.randomUUID();
    localStorage.setItem(VISITOR_KEY, fresh);
    return fresh;
  } catch {
    memoryVisitor ??= crypto.randomUUID();
    return memoryVisitor;
  }
}

/** The allowance ring: fills down as today's AI allowance is used. */
export function QuotaRing({ quota, size = 34 }: { quota: Quota; size?: number }) {
  const { t, f } = useI18n();
  const A = t.launch.ask;
  const left = Math.max(0, Math.min(100, quota.left_percent));
  const r = 15;
  const c = 2 * Math.PI * r;
  const tone = left > 30 ? "text-brand-500" : left > 10 ? "text-amber-500" : "text-red-500";
  const label = quota.exhausted ? A.ringEmpty : A.ringLabel(f.num(left), f.num(quota.answers_left));
  return (
    <div className="group relative flex items-center" title={label} aria-label={label} role="img">
      <svg width={size} height={size} viewBox="0 0 36 36" className="-rotate-90">
        <circle cx="18" cy="18" r={r} fill="none" strokeWidth="3.5" className="stroke-slate-200" />
        <circle
          cx="18"
          cy="18"
          r={r}
          fill="none"
          strokeWidth="3.5"
          strokeLinecap="round"
          stroke="currentColor"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - left / 100)}
          className={cx(tone, "transition-[stroke-dashoffset] duration-700 ease-out")}
        />
      </svg>
      <span className="num absolute inset-0 flex items-center justify-center text-[10px] font-bold text-ink-900">{f.num(left)}</span>
    </div>
  );
}

export function AskReplisto({ compact, onClose }: { compact?: boolean; onClose?: () => void }) {
  const { t, f } = useI18n();
  const A = t.launch.ask;
  const { loggedIn } = useAuth();
  const qc = useQueryClient();
  const visitor = useRef(visitorId()).current;
  const key = ["site-chat", visitor, loggedIn] as const;
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const chat = useQuery({
    queryKey: key,
    queryFn: () => api<SiteChat>("/site/chat", { query: { visitor }, auth: loggedIn }),
    // While the team is answering, look for their reply.
    refetchInterval: (q) => (q.state.data?.waiting_for_team ? 5_000 : false),
  });

  const send = useMutation({
    mutationFn: (message: string) => api<SiteChat>("/site/chat", { method: "POST", json: { visitor, text: message }, auth: loggedIn }),
    onMutate: (message) => setPending(message),
    onSuccess: (data) => qc.setQueryData(key, data),
    onError: () => qc.invalidateQueries({ queryKey: key }),
    onSettled: () => setPending(null),
  });

  const messages = chat.data?.messages ?? [];
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages.length, pending]);

  function ask(message: string) {
    const clean = message.trim();
    if (!clean || send.isPending) return;
    setText("");
    send.mutate(clean);
  }
  function onSubmit(e: FormEvent) {
    e.preventDefault();
    ask(text);
  }

  const quota = chat.data?.quota;
  const exhausted = Boolean(quota?.exhausted);
  const unavailable = chat.data && !chat.data.available;

  return (
    <div className={cx("flex flex-col overflow-hidden rounded-3xl bg-surface shadow-lift ring-1 ring-line", compact ? "h-full" : "h-[34rem]")}>
      <div className="flex items-center gap-3 border-b border-slate-100 px-4 py-3">
        <LogoMark px={36} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-bold text-ink-950">{A.botName}</div>
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <span aria-hidden className="size-1.5 rounded-full bg-emerald-500" />
            <span className="truncate">{A.status}</span>
          </div>
        </div>
        {quota && <QuotaRing quota={quota} />}
        {onClose && (
          <button type="button" onClick={onClose} aria-label={t.common.close} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-ink-950">
            <X className="size-5" />
          </button>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4" aria-live="polite">
        {unavailable ? (
          <div className="flex flex-1 items-center justify-center text-center text-sm text-slate-500">{A.unavailable}</div>
        ) : messages.length === 0 && !pending ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
            <span className="flex size-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
              <Sparkles className="size-6" />
            </span>
            <p className="max-w-xs text-sm font-semibold text-ink-900">{A.empty}</p>
            <div className="flex flex-wrap justify-center gap-2">
              {A.suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  disabled={exhausted || send.isPending}
                  onClick={() => ask(s)}
                  className="rounded-full bg-surface px-3 py-1.5 text-xs font-medium text-ink-800 ring-1 ring-slate-200 transition-[box-shadow,color] hover:text-brand-700 hover:ring-brand-300 disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((m) => (
              <div key={m.id} className={cx("animate-fade-in flex", m.sender === "customer" ? "justify-start" : "justify-end")}>
                <div
                  className={cx(
                    "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-7",
                    m.sender === "customer" ? "rounded-ss-md bg-slate-100 text-ink-950" : "rounded-se-md bg-brand-50 text-ink-950",
                  )}
                >
                  {m.sender === "owner" && (
                    <div className="mb-1 flex items-center gap-1 text-[11px] font-bold text-brand-700">
                      <UsersRound className="size-3.5" aria-hidden />
                      {A.team}
                    </div>
                  )}
                  <MessageText text={m.text} />
                </div>
              </div>
            ))}
            {pending && (
              <>
                <div className="flex justify-start">
                  <div className="max-w-[85%] rounded-2xl rounded-ss-md bg-slate-100 px-3.5 py-2.5 text-sm leading-7 text-ink-950 opacity-70">{pending}</div>
                </div>
                <div className="flex justify-end" role="status" aria-label={A.typing}>
                  <div className="flex items-center gap-1 rounded-2xl rounded-se-md bg-brand-50 px-4 py-3.5">
                    <span className="typing-dot size-1.5 rounded-full bg-brand-500" />
                    <span className="typing-dot size-1.5 rounded-full bg-brand-500 [animation-delay:0.2s]" />
                    <span className="typing-dot size-1.5 rounded-full bg-brand-500 [animation-delay:0.4s]" />
                  </div>
                </div>
              </>
            )}
            {chat.data?.waiting_for_team && <p className="text-center text-xs text-slate-500">{A.waiting}</p>}
          </>
        )}
        {send.error && <Alert kind="error">{errorMessage(send.error, t)}</Alert>}
        <div ref={bottom} />
      </div>

      {exhausted && quota ? (
        <div className="space-y-3 border-t border-slate-100 p-4 text-center">
          <p className="text-sm text-slate-600">
            {quota.tier === "guest" ? A.guestLimit : A.memberLimit(f.time(quota.resets_at))}
          </p>
          {quota.tier === "guest" && (
            <div className="flex justify-center gap-2">
              <Link to="/register" className={buttonClass("primary", "sm")}>
                {A.signUp}
              </Link>
              <Link to="/login" className={buttonClass("secondary", "sm")}>
                {A.logIn}
              </Link>
            </div>
          )}
        </div>
      ) : (
        <form onSubmit={onSubmit} className="border-t border-slate-100 p-3">
          <div className="flex items-end gap-2 rounded-2xl bg-slate-50 p-1.5 ring-1 ring-slate-200 transition-shadow focus-within:bg-surface focus-within:ring-2 focus-within:ring-brand-400">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value.slice(0, 600))}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  ask(text);
                }
              }}
              rows={1}
              placeholder={A.placeholder}
              aria-label={A.placeholder}
              disabled={Boolean(unavailable)}
              className="max-h-28 min-h-10 flex-1 resize-none bg-transparent px-3 py-2 text-sm leading-6 text-ink-950 placeholder:text-slate-400 focus:outline-none"
            />
            <Button type="submit" disabled={!text.trim() || send.isPending || Boolean(unavailable)} aria-label={A.send} className="size-10 shrink-0 !px-0">
              <Send className="size-4 rtl:-scale-x-100" aria-hidden />
            </Button>
          </div>
          {quota?.tier === "guest" && <p className="mt-2 px-1 text-[11px] text-slate-400">{A.guestHint}</p>}
        </form>
      )}
    </div>
  );
}

/** The panel's floating "Ask Replisto" button and its chat window. */
export function AskReplistoLauncher() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  return (
    <>
      {open && (
        <div className="fixed inset-x-3 bottom-[calc(var(--chrome-bottom)+5rem)] z-40 h-[min(32rem,calc(100dvh-var(--chrome-bottom)-7rem))] sm:inset-x-auto sm:end-6 sm:w-96">
          <AskReplisto compact onClose={() => setOpen(false)} />
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={t.launch.ask.launcher}
        title={t.launch.ask.launcher}
        className="fixed end-4 bottom-[calc(var(--chrome-bottom)+1rem)] z-40 flex size-13 items-center justify-center rounded-full bg-brand-600 text-white shadow-lift transition-transform hover:scale-105 active:scale-95 sm:end-6"
      >
        {open ? <X className="size-6" /> : <MessageCircleQuestion className="size-6" />}
      </button>
    </>
  );
}
