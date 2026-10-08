import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { CreditCard, History, Wallet } from "lucide-react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Billing as BillingData, WalletEntryPage } from "../api/types";
import { useToast } from "../components/toast";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, Field, Input, PageHeader, PageLoading, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";

export default function Billing() {
  const { t } = useI18n();
  const B = t.launch.billing;
  const [params, setParams] = useSearchParams();
  // back from the payment gateway: ?payment=success[&ref=…] | ?payment=pending | ?payment=failed
  const payment = params.get("payment");
  const ref = params.get("ref") ?? "";
  const [notice] = useState(payment);
  // Some payment methods are confirmed a little after the owner is back, so keep checking the
  // balance for a couple of minutes.
  const [watchUntil] = useState(() => (payment === "pending" ? Date.now() + 120_000 : 0));
  const billing = useQuery({
    queryKey: keys.billing,
    queryFn: () => api<BillingData>("/billing"),
    refetchInterval: () => (Date.now() < watchUntil ? 5_000 : false),
  });
  useEffect(() => {
    if (payment) setParams({}, { replace: true });
  }, [payment, setParams]);

  const header = <PageHeader icon={<Wallet />} title={B.title} subtitle={B.subtitle} />;
  if (billing.isPending)
    return (
      <>
        {header}
        <PageLoading />
      </>
    );
  if (billing.error)
    return (
      <>
        {header}
        <Alert kind="error">{errorMessage(billing.error, t)}</Alert>
      </>
    );
  const b = billing.data;

  return (
    <div className="max-w-5xl space-y-6">
      {header}
      {notice === "success" && <Alert kind="success">{ref ? B.paymentSuccess(ref) : B.paymentSuccessNoRef}</Alert>}
      {notice === "pending" && <Alert kind="info">{B.paymentPending}</Alert>}
      {notice === "failed" && <Alert kind="error">{B.paymentFailed}</Alert>}
      {!b.enabled && <Alert kind="info">{B.disabled}</Alert>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <Balance b={b} />
        <Topup b={b} />
      </div>
      <Pricing b={b} />
      <HistoryCard />
    </div>
  );
}

function Balance({ b }: { b: BillingData }) {
  const { t, f } = useI18n();
  const B = t.launch.billing;
  return (
    <section className="animate-pop-in relative overflow-hidden rounded-3xl bg-brand-600 p-6 text-white shadow-lift lg:col-span-2">
      <div className="text-sm font-semibold text-white/75">{B.balance}</div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="num text-4xl font-extrabold">{f.usd(b.balance_cents)}</span>
      </div>
      <div className="mt-4 text-sm text-white/80">{B.perAnswer(f.usd(b.pricing.typical_answer_cents))}</div>
      {b.low_balance && <div className="mt-4 rounded-xl bg-white/15 px-3 py-2 text-sm font-semibold">{t.launch.lowBalance(f.usd(b.balance_cents))}</div>}
    </section>
  );
}

function Topup({ b }: { b: BillingData }) {
  const { t, f } = useI18n();
  const B = t.launch.billing;
  const toast = useToast();
  const [amount, setAmount] = useState("");
  // typed in dollars, sent in cents
  const dollars = Number(amount.replace(/[^\d.]/g, ""));
  const value = Number.isFinite(dollars) ? Math.round(dollars * 100) : 0;
  const presets = [1_000, 2_500, 5_000, 10_000].filter((v) => v >= b.topup_min_cents && v <= b.topup_max_cents);

  const pay = useMutation({
    mutationFn: () => api<{ payment_url: string }>("/billing/topup", { method: "POST", json: { amount_cents: value } }),
    onSuccess: ({ payment_url }) => {
      window.location.href = payment_url;
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  return (
    <Card className="lg:col-span-3">
      <CardHeader icon={<CreditCard />} title={B.topupTitle} />
      <div className="space-y-4 p-5 sm:px-6">
        {!b.topup_available ? (
          <Alert kind="info">{B.topupUnavailable}</Alert>
        ) : (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              pay.mutate();
            }}
          >
            <div className="flex flex-wrap gap-2">
              {presets.map((p) => (
                <Button key={p} size="sm" variant={value === p ? "primary" : "secondary"} onClick={() => setAmount(String(p / 100))}>
                  <span className="num">{f.usd(p)}</span>
                </Button>
              ))}
            </div>
            <Field label={B.amount} hint={B.amountHint(f.usd(b.topup_min_cents), f.usd(b.topup_max_cents))}>
              {(id) => <Input id={id} inputMode="decimal" dir="ltr" placeholder="25" value={amount} onChange={(e) => setAmount(e.target.value)} />}
            </Field>
            <Button type="submit" loading={pay.isPending} disabled={!value || value < b.topup_min_cents || value > b.topup_max_cents}>
              {pay.isPending ? B.redirecting : B.pay}
            </Button>
            <p className="text-xs text-slate-500">
              {B.nonRefundable}{" "}
              <Link to="/terms#wallet" className="font-medium text-brand-700 hover:underline">
                {B.termsLink}
              </Link>
            </p>
          </form>
        )}
      </div>
    </Card>
  );
}

function Pricing({ b }: { b: BillingData }) {
  const { t, f } = useI18n();
  const B = t.launch.billing;
  return (
    <Card className="p-5 sm:p-6">
      <h2 className="font-bold text-ink-950">{B.pricingTitle}</h2>
      <ul className="mt-3 list-disc space-y-1.5 ps-5 text-sm leading-6 text-slate-600">
        <li>{B.pricingAnswer}</li>
        <li>{B.perAnswer(f.usd(b.pricing.typical_answer_cents))}</li>
        <li>{B.pricingMin(f.usd(b.pricing.min_per_answer_cents))}</li>
      </ul>
    </Card>
  );
}

function HistoryCard() {
  const { t, f } = useI18n();
  const B = t.launch.billing;
  const list = useInfiniteQuery({
    queryKey: keys.walletEntries,
    queryFn: ({ pageParam }) => api<WalletEntryPage>("/billing/entries", { query: { offset: pageParam, limit: 30 } }),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((n, p) => n + p.items.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
  });
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <Card>
      <CardHeader icon={<History />} title={B.historyTitle} />
      {list.isPending ? (
        <PageLoading />
      ) : list.error ? (
        <div className="p-5">
          <Alert kind="error">{errorMessage(list.error, t)}</Alert>
        </div>
      ) : items.length === 0 ? (
        <EmptyState icon={<History />} title={B.historyEmpty} />
      ) : (
        <ul className="divide-y divide-slate-100">
          {items.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center gap-3 px-5 py-3 sm:px-6">
              <Badge tone={e.amount_cents >= 0 ? "green" : "neutral"}>{B.kinds[e.kind] ?? e.kind}</Badge>
              <span className="min-w-0 flex-1 truncate text-sm text-ink-900">{e.description}</span>
              <span className="text-xs text-slate-400">{f.smart(e.created_at)}</span>
              <span className={cx("num w-28 text-end text-sm font-bold", e.amount_cents >= 0 ? "text-emerald-700" : "text-ink-900")}>
                {e.amount_cents >= 0 ? "+" : "−"}
                {f.usd(Math.abs(e.amount_cents))}
              </span>
            </li>
          ))}
        </ul>
      )}
      {list.hasNextPage && (
        <div className="border-t border-slate-100 p-3 text-center">
          <Button size="sm" variant="ghost" loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>
            {t.common.loadMore}
          </Button>
        </div>
      )}
    </Card>
  );
}
