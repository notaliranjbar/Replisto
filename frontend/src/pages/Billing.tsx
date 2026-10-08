import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CreditCard, History, Layers, Wallet } from "lucide-react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Billing as BillingData, Plan, WalletEntryPage } from "../api/types";
import { useToast } from "../components/toast";
import { Alert, Badge, Button, Card, CardHeader, ConfirmDialog, EmptyState, Field, Input, PageHeader, PageLoading, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage, isPersian } from "../lib/errors";

export default function Billing() {
  const { t } = useI18n();
  const B = t.launch.billing;
  const [params, setParams] = useSearchParams();
  // back from the payment gateway: ?payment=success[&ref=…] | ?payment=pending | ?payment=failed
  const payment = params.get("payment");
  const ref = params.get("ref") ?? "";
  const [notice] = useState(payment);
  // Card-to-card (Aban): the bank SMS may confirm it a few seconds after the owner is back,
  // so keep checking the balance for a couple of minutes.
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
      <Plans b={b} />
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
        <span className="num text-4xl font-extrabold">{f.num(b.balance_toman)}</span>
        <span className="text-sm text-white/80">{B.toman}</span>
      </div>
      <div className="mt-4 text-sm text-white/80">{B.perAnswer(f.num(b.pricing.typical_answer_toman))}</div>
      {b.low_balance && <div className="mt-4 rounded-xl bg-white/15 px-3 py-2 text-sm font-semibold">{t.launch.lowBalance(f.num(b.balance_toman))}</div>}
    </section>
  );
}

function Topup({ b }: { b: BillingData }) {
  const { t, f } = useI18n();
  const B = t.launch.billing;
  const toast = useToast();
  const [amount, setAmount] = useState("");
  const value = Number(amount.replace(/[^\d]/g, ""));
  const presets = [100_000, 300_000, 1_000_000].filter((v) => v >= b.topup_min_toman && v <= b.topup_max_toman);

  const pay = useMutation({
    mutationFn: () => api<{ payment_url: string }>("/billing/topup", { method: "POST", json: { amount_toman: value } }),
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
                <Button key={p} size="sm" variant={value === p ? "primary" : "secondary"} onClick={() => setAmount(String(p))}>
                  <span className="num">{f.num(p)}</span>
                </Button>
              ))}
            </div>
            <Field label={B.amount} hint={B.amountHint(f.num(b.topup_min_toman), f.num(b.topup_max_toman))}>
              {(id) => <Input id={id} inputMode="numeric" dir="ltr" value={amount} onChange={(e) => setAmount(e.target.value)} />}
            </Field>
            <Button type="submit" loading={pay.isPending} disabled={!value || value < b.topup_min_toman || value > b.topup_max_toman}>
              {pay.isPending ? B.redirecting : B.pay}
            </Button>
            {b.gateway === "aban" && <p className="text-sm leading-6 text-slate-600">{B.cardToCardHint}</p>}
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

function Plans({ b }: { b: BillingData }) {
  const { t, f } = useI18n();
  const B = t.launch.billing;
  const toast = useToast();
  const qc = useQueryClient();
  const [target, setTarget] = useState<Plan | null>(null);
  const current = b.plans.findIndex((p) => p.key === b.plan);

  const change = useMutation({
    mutationFn: (plan: string) => api<BillingData>("/billing/plan", { method: "POST", json: { plan } }),
    onSuccess: (data) => {
      qc.setQueryData(keys.billing, data);
      qc.invalidateQueries({ queryKey: keys.walletEntries });
      qc.invalidateQueries({ queryKey: keys.telegram });
      qc.invalidateQueries({ queryKey: keys.dashboard });
      setTarget(null);
      toast.success(B.planChanged);
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  // plan names and features come from the API in Persian; show our own copy for known plans
  const plans = b.plans.map((p): Plan => {
    const copy = B.plans[p.key];
    return copy ? { ...p, label: copy.label, features: [...copy.features] } : p;
  });
  const upgrading = target ? plans.findIndex((p) => p.key === target.key) > current : false;
  const nextLabel = plans.find((p) => p.key === b.plan_next)?.label;

  return (
    <Card>
      <CardHeader icon={<Layers />} title={B.plansTitle} />
      <div className="grid grid-cols-1 gap-4 p-5 sm:px-6 md:grid-cols-3">
        {plans.map((p) => {
          const active = p.key === b.plan;
          return (
            <div key={p.key} className={cx("flex flex-col rounded-2xl p-5 ring-1", active ? "bg-brand-50/70 ring-brand-300" : "ring-line")}>
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-lg font-extrabold text-ink-950">{p.label}</h3>
                {active && <Badge tone="brand">{B.currentPlan}</Badge>}
              </div>
              <div className="mt-1 text-sm font-semibold text-slate-500">{p.monthly_fee_toman ? B.monthly(f.num(p.monthly_fee_toman)) : B.free}</div>
              <ul className="mt-4 flex-1 space-y-2 text-sm leading-6 text-slate-600">
                {p.features.map((feature) => (
                  <li key={feature} className="flex gap-2">
                    <Check className="mt-1 size-4 shrink-0 text-emerald-500" aria-hidden />
                    {feature}
                  </li>
                ))}
              </ul>
              {active ? (
                b.plan_renews_at && <p className="mt-4 text-xs text-slate-500">{B.renewsAt(f.date(b.plan_renews_at))}</p>
              ) : (
                <Button className="mt-4" variant={b.plan_next === p.key ? "soft" : "secondary"} onClick={() => setTarget(p)} disabled={b.plan_next === p.key}>
                  {B.choose}
                </Button>
              )}
            </div>
          );
        })}
      </div>
      {nextLabel && b.plan_renews_at && (
        <div className="px-5 pb-5 sm:px-6">
          <Alert
            kind="info"
            action={
              <Button size="sm" variant="secondary" loading={change.isPending} onClick={() => change.mutate(b.plan)}>
                {B.cancelChange}
              </Button>
            }
          >
            {B.nextPlan(nextLabel, f.date(b.plan_renews_at))}
          </Alert>
        </div>
      )}
      <ConfirmDialog
        open={target !== null}
        onClose={() => setTarget(null)}
        onConfirm={() => target && change.mutate(target.key)}
        loading={change.isPending}
        title={target ? (upgrading ? B.upgradeConfirmTitle(target.label) : B.downgradeConfirmTitle(target.label)) : ""}
        body={target ? (upgrading ? B.upgradeConfirmBody(f.num(target.monthly_fee_toman)) : B.downgradeConfirmBody) : ""}
        confirmLabel={B.choose}
        cancelLabel={t.common.cancel}
      />
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
        <li>{B.perAnswer(f.num(b.pricing.typical_answer_toman))}</li>
        <li>{B.pricingMin(f.num(b.pricing.min_per_answer_toman))}</li>
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
              <Badge tone={e.amount_toman >= 0 ? "green" : "neutral"}>{B.kinds[e.kind] ?? e.kind}</Badge>
              <span className="min-w-0 flex-1 truncate text-sm text-ink-900">{isPersian(e.description) ? "" : e.description}</span>
              <span className="text-xs text-slate-400">{f.smart(e.created_at)}</span>
              <span className={cx("num w-28 text-end text-sm font-bold", e.amount_toman >= 0 ? "text-emerald-700" : "text-ink-900")}>
                {e.amount_toman >= 0 ? "+" : "−"}
                {f.num(Math.abs(Math.round(e.amount_toman)))}
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
