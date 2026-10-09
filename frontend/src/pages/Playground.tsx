import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, BookOpen, ChevronDown, FlaskConical, Lightbulb, PackageSearch, RotateCcw, Send, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { api } from "../api/client";
import { useMe } from "../api/queries";
import type { PlaygroundReply, PlaygroundTurn } from "../api/types";
import { LogoMark } from "../components/Logo";
import { PostCard } from "../components/PostCard";
import { Alert, Badge, Button, Card, IconChip, PageHeader, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";
import { playgroundKey, setFlag } from "../lib/storage";

const MAX_TURNS = 30; // API limit for the whole history

type Turn = PlaygroundTurn & { reply?: PlaygroundReply };

export default function Playground() {
  const { t } = useI18n();
  const { data: me } = useMe();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [aiReady, setAiReady] = useState(true);
  const [sent, setSent] = useState(0); // restarts the send button's paper-plane animation
  const bottom = useRef<HTMLDivElement>(null);

  const chat = useMutation({
    // the panel keeps the history and sends all of it each time; nothing is stored server-side
    mutationFn: (history: Turn[]) =>
      api<PlaygroundReply>("/playground/chat", { method: "POST", json: { messages: history.map(({ role, text }) => ({ role, text })) } }),
    onSuccess: (reply) => {
      setAiReady(reply.ai_ready);
      setTurns((list) => [...list, { role: "bot", text: reply.reply, reply }]);
      if (me) setFlag(playgroundKey(me.shop.id));
    },
  });

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, chat.isPending]);

  const full = turns.length >= MAX_TURNS - 1;

  function send(message: string) {
    const clean = message.trim();
    if (!clean || chat.isPending || full) return;
    const history: Turn[] = [...turns, { role: "customer", text: clean.slice(0, 2000) }];
    setTurns(history);
    setText("");
    setSent((n) => n + 1);
    chat.mutate(history);
  }

  function retry() {
    if (turns.at(-1)?.role === "customer") chat.mutate(turns);
  }

  function restart() {
    chat.reset();
    setTurns([]);
    setText("");
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send(text);
  }

  return (
    <div className="flex h-[calc(100dvh-var(--chrome-top)-var(--chrome-bottom)-3rem)] min-h-[34rem] flex-col lg:h-[calc(100dvh-5rem)]">
      <PageHeader icon={<FlaskConical />} title={t.playground.title} subtitle={t.playground.subtitle} />

      {!aiReady && <Alert kind="info" className="mb-4">{t.playground.aiNotReady}</Alert>}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <Card className="flex min-h-0 flex-col overflow-hidden">
          <div className="flex items-center gap-3 border-b border-slate-100 px-4 py-3 sm:px-5">
            <LogoMark px={36} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-ink-950">{t.panel.playground.botName(me?.shop.name ?? t.appName)}</div>
              <span className="mt-0.5 inline-flex rounded-full bg-accent-300 px-2 text-[11px] font-semibold leading-5 text-night-900">{t.panel.playground.env}</span>
            </div>
            {turns.length > 0 && (
              <Button variant="ghost" size="sm" icon={<RotateCcw className="size-4" />} onClick={restart}>
                {t.playground.restart}
              </Button>
            )}
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
            {turns.length === 0 && (
              <div className="animate-pop-in flex h-full flex-col items-center justify-center gap-4 py-6 text-center">
                <LogoMark px={56} className="shadow-lift" />
                <p className="max-w-xs font-semibold text-ink-900">{t.playground.empty}</p>
                <div className="flex max-w-lg flex-wrap justify-center gap-2">
                  {t.playground.suggestions.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => send(s)}
                      className="rounded-full bg-surface px-3.5 py-2 text-sm font-medium text-ink-800 ring-1 ring-slate-200 transition-[box-shadow,color,transform] duration-200 hover:-translate-y-0.5 hover:text-brand-700 hover:shadow-soft hover:ring-brand-300 active:translate-y-0"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {turns.map((turn, i) => (turn.role === "customer" ? <CustomerBubble key={i} text={turn.text} /> : <BotBubble key={i} turn={turn} />))}

            {chat.isPending && (
              <div className="animate-fade-in flex justify-end" role="status" aria-label={t.playground.typing}>
                <div className="flex items-center gap-1 rounded-2xl rounded-se-md bg-brand-50 px-4 py-3.5">
                  <span className="typing-dot size-1.5 rounded-full bg-brand-500" />
                  <span className="typing-dot size-1.5 rounded-full bg-brand-500 [animation-delay:0.2s]" />
                  <span className="typing-dot size-1.5 rounded-full bg-brand-500 [animation-delay:0.4s]" />
                </div>
              </div>
            )}

            {chat.error && (
              <Alert kind="error" action={<Button size="sm" variant="secondary" onClick={retry}>{t.common.retry}</Button>}>
                {errorMessage(chat.error, t)}
              </Alert>
            )}
            {full && <Alert kind="warning">{t.playground.limit}</Alert>}
            <div ref={bottom} />
          </div>

          <form onSubmit={onSubmit} className="border-t border-slate-100 p-3 sm:p-4">
            <div className="flex items-end gap-2 rounded-2xl bg-slate-50 p-1.5 ring-1 ring-slate-200 transition-shadow focus-within:bg-surface focus-within:ring-2 focus-within:ring-brand-400">
              <textarea
                rows={1}
                className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-3 py-2 text-sm leading-6 text-ink-950 placeholder:text-slate-400 focus:outline-none disabled:opacity-60"
                placeholder={t.playground.placeholder}
                aria-label={t.playground.placeholder}
                value={text}
                maxLength={2000}
                disabled={full}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    send(text);
                  }
                }}
              />
              <Button type="submit" disabled={!text.trim() || chat.isPending || full} aria-label={t.playground.send} className="size-10 shrink-0 !px-0">
                <Send key={sent} className={cx("size-4 rtl:-scale-x-100", sent > 0 && "animate-send")} aria-hidden />
              </Button>
            </div>
          </form>
        </Card>

        <Tips />
      </div>
    </div>
  );
}

/** Desktop side rail: what to try, the promise that nothing is sent, where to improve answers. */
function Tips() {
  const { t } = useI18n();
  const P = t.panel.playground;
  return (
    <aside className="hidden min-h-0 space-y-4 overflow-y-auto lg:block">
      <Card className="p-5">
        <div className="flex items-center gap-2.5">
          <IconChip>
            <Lightbulb />
          </IconChip>
          <h2 className="text-sm font-semibold text-ink-950">{P.tipsTitle}</h2>
        </div>
        <ul className="mt-4 space-y-2.5">
          {P.tips.map((tip) => (
            <li key={tip} className="flex gap-2.5 text-sm leading-6 text-slate-600">
              <span aria-hidden className="mt-2.5 size-1.5 shrink-0 rounded-full bg-brand-500" />
              {tip}
            </li>
          ))}
        </ul>
      </Card>
      <div className="flex gap-3 rounded-2xl bg-emerald-50 p-4 text-sm leading-6 text-emerald-900 ring-1 ring-emerald-200/80">
        <ShieldCheck className="mt-0.5 size-5 shrink-0 text-emerald-600" aria-hidden />
        {P.safe}
      </div>
      <Card className="p-2">
        <div className="px-3 pb-1 pt-2 text-xs font-semibold text-slate-400">{P.improveTitle}</div>
        {[
          { to: "/knowledge", icon: <BookOpen />, label: t.nav.knowledge },
          { to: "/settings", icon: <SlidersHorizontal />, label: t.nav.settings },
        ].map((l) => (
          <Link key={l.to} to={l.to} className="group flex items-center gap-3 rounded-xl p-3 text-sm font-semibold text-ink-900 transition-colors hover:bg-brand-50/70">
            <IconChip>{l.icon}</IconChip>
            <span className="flex-1">{l.label}</span>
            <ArrowRight className="size-4 text-slate-300 transition-[transform,color] group-hover:translate-x-0.5 group-hover:text-brand-700 rtl:-scale-x-100 rtl:group-hover:-translate-x-0.5" aria-hidden />
          </Link>
        ))}
      </Card>
    </aside>
  );
}

function CustomerBubble({ text }: { text: string }) {
  return (
    <div className="animate-msg-in flex justify-start">
      <div className="user-text max-w-[85%] rounded-2xl rounded-ss-md bg-slate-100 px-4 py-2.5 text-sm leading-7 text-ink-900 sm:max-w-[70%]">{text}</div>
    </div>
  );
}

function BotBubble({ turn }: { turn: Turn }) {
  const { t } = useI18n();
  const r = turn.reply;
  return (
    <div className="animate-msg-in flex flex-col items-end gap-2">
      <div className="flex max-w-[85%] items-end gap-2 sm:max-w-[70%]">
        <div className="user-text rounded-2xl rounded-se-md bg-brand-600 px-4 py-2.5 text-sm leading-7 text-white">{turn.text}</div>
        <LogoMark px={26} className="mb-0.5 rounded-lg" />
      </div>

      {r?.unanswered && (
        <div className="me-9 max-w-[85%] rounded-xl bg-amber-50 px-3.5 py-2.5 text-xs leading-5 text-amber-900 ring-1 ring-amber-200 sm:max-w-[70%]">
          <div className="font-semibold">{t.playground.unansweredLabel}</div>
          {r.handoff_reason && (
            <div className="mt-0.5 opacity-80">
              {t.playground.reason}: {r.handoff_reason}
            </div>
          )}
          <Link to="/knowledge" className="mt-1 inline-block font-semibold text-amber-800 underline underline-offset-2">
            {t.playground.unansweredAdd}
          </Link>
        </div>
      )}

      {r?.posts.map((post) => <PostCard key={post.permalink} post={post} className="me-9" />)}

      {r && r.product_lookups.some((l) => l.tool === "search_products") && (
        <Lookups lookups={r.product_lookups.filter((l) => l.tool === "search_products")} />
      )}
    </div>
  );
}

type Lookup = { tool?: string; arguments?: Record<string, unknown>; result?: { matches?: ProductInfo[]; other_in_stock_variants?: ProductInfo[] } };
type ProductInfo = { name?: string; color?: string; size?: string; price?: number; in_stock?: boolean; stock_count?: number; sku?: string };

/** "The bot checked these products" — shows owners why the bot said what it said. */
function Lookups({ lookups }: { lookups: Record<string, unknown>[] }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const items = lookups as Lookup[];

  return (
    <div className="me-9 w-full max-w-[85%] overflow-hidden rounded-xl bg-surface text-xs ring-1 ring-slate-200 sm:max-w-[70%]">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 font-semibold text-slate-600 transition-colors hover:bg-slate-50"
      >
        <PackageSearch className="size-4 text-brand-500" aria-hidden />
        <span className="flex-1 text-start">{t.playground.lookups}</span>
        <ChevronDown className={cx("size-4 transition-transform duration-200", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div className="animate-pop-in space-y-3 border-t border-slate-100 px-3.5 py-3">
          {items.map((l, i) => {
            const args = Object.entries(l.arguments ?? {}).filter(([, v]) => v !== null && v !== "");
            const matches = l.result?.matches ?? [];
            const others = l.result?.other_in_stock_variants ?? [];
            return (
              <div key={i}>
                <div className="mb-1.5 flex flex-wrap items-center gap-1 text-slate-500">
                  {t.playground.lookupQuery}:
                  {args.map(([k, v]) => (
                    <Badge key={k}>{String(v)}</Badge>
                  ))}
                </div>
                {matches.length === 0 && <div className="text-slate-400">{t.playground.lookupNoMatch}</div>}
                <ProductList items={matches} />
                {others.length > 0 && (
                  <>
                    <div className="mb-1.5 mt-2.5 text-slate-500">{t.playground.otherVariants}</div>
                    <ProductList items={others} />
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ProductList({ items }: { items: ProductInfo[] }) {
  const { t, f } = useI18n();
  const currency = useMe().data?.shop.currency ?? "USD";
  if (!items.length) return null;
  return (
    <ul className="divide-y divide-slate-100 rounded-lg bg-slate-50">
      {items.map((p, i) => (
        <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-2.5 py-2">
          <span className="font-semibold text-ink-900">{p.name}</span>
          {p.color && <span className="text-slate-500">{p.color}</span>}
          {p.size && <span className="num text-slate-500">{p.size}</span>}
          {p.price != null && <span className="num text-ink-800">{f.money(p.price, currency)}</span>}
          {p.in_stock === false && <Badge tone="red">{t.products.outOfStock}</Badge>}
          {p.in_stock && p.stock_count != null && <span className="num font-semibold text-emerald-700">× {f.num(p.stock_count)}</span>}
        </li>
      ))}
    </ul>
  );
}
