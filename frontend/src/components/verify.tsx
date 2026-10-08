// Email and phone verification, and the sign-up gift card that asks for them.
import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Gift, Mail, ShieldCheck, Smartphone } from "lucide-react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { Dashboard, User } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";
import AuthShell from "./AuthShell";
import { useToast } from "./toast";
import { Alert, Badge, Button, Card, CardHeader, Field, IconChip, Input, LinkButton, Spinner, cx } from "./ui";

type PhoneStart = { phone: string; minutes: number };
type PhoneVerified = { phone: string; gift_toman: number };

function localPhone(phone: string) {
  return phone.startsWith("+98") ? "0" + phone.slice(3) : phone;
}

/** "Resend the link" for an unverified email. */
export function useResendEmail() {
  const { t } = useI18n();
  const toast = useToast();
  return useMutation({
    mutationFn: () => api<{ message: string }>("/auth/email/resend", { method: "POST" }),
    onSuccess: (r) => toast.success(r.message),
    onError: (err) => toast.error(errorMessage(err, t)),
  });
}

/** Shown instead of the panel until the email is verified; opens by itself once the link is clicked (here or on another device). */
export function CheckYourEmail({ me }: { me: User }) {
  const { t } = useI18n();
  const V = t.launch.verify;
  const { logout } = useAuth();
  const resend = useResendEmail();
  useQuery({ queryKey: keys.me, queryFn: () => api<User>("/me"), refetchInterval: 4000 });
  return (
    <AuthShell
      title={V.gateTitle}
      subtitle={V.gateSubtitle}
      footer={
        <>
          {V.wrongEmail}{" "}
          <button type="button" onClick={logout} className="font-medium text-brand-700 hover:underline">
            {V.signUpAgain}
          </button>
        </>
      }
    >
      <div className="space-y-5">
        <div className="flex items-start gap-4">
          <IconChip>
            <Mail />
          </IconChip>
          <p className="text-sm leading-7 text-ink-800">{V.gateBody(me.email)}</p>
        </div>
        <p className="text-sm leading-6 text-slate-500">{V.gateSpam}</p>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="secondary" loading={resend.isPending} onClick={() => resend.mutate()}>
            {V.resend}
          </Button>
          <span className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner className="size-4" />
            {V.gateWaiting}
          </span>
        </div>
      </div>
    </AuthShell>
  );
}

export function EmailNotVerified({ me }: { me: User }) {
  const { t } = useI18n();
  const resend = useResendEmail();
  if (me.email_verified_at) return null;
  return (
    <Alert
      kind="info"
      action={
        <Button size="sm" variant="secondary" loading={resend.isPending} onClick={() => resend.mutate()}>
          {t.launch.verify.resend}
        </Button>
      }
    >
      {t.launch.verify.banner(me.email)}
    </Alert>
  );
}

/** Account page: the email's state and the phone form (send code → type code). */
export function VerificationCard({ me }: { me: User }) {
  const { t } = useI18n();
  const V = t.launch.verify;
  const resend = useResendEmail();
  return (
    <Card>
      <CardHeader icon={<ShieldCheck />} title={V.title} />
      <div className="divide-y divide-slate-100">
        <div className="flex flex-wrap items-center gap-3 p-5 sm:px-6">
          <Mail className="size-5 text-slate-400" aria-hidden />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-ink-900">{V.email}</div>
            <div className="ltr truncate text-sm text-slate-500">{me.email}</div>
          </div>
          {me.email_verified_at ? (
            <Badge tone="green">
              <Check aria-hidden />
              {V.verified}
            </Badge>
          ) : (
            <>
              <Badge tone="amber">{V.notVerified}</Badge>
              <Button size="sm" variant="secondary" loading={resend.isPending} onClick={() => resend.mutate()}>
                {V.resend}
              </Button>
            </>
          )}
        </div>
        <div id="phone" className="p-5 sm:px-6">
          <PhoneForm me={me} />
        </div>
      </div>
    </Card>
  );
}

function PhoneForm({ me }: { me: User }) {
  const { t, f } = useI18n();
  const V = t.launch.verify;
  const toast = useToast();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(!me.phone_verified_at);
  const [number, setNumber] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState<PhoneStart | null>(null);

  const start = useMutation({
    mutationFn: () => api<PhoneStart>("/me/phone", { method: "POST", json: { phone: number } }),
    onSuccess: (r) => {
      setSent(r);
      setCode("");
    },
  });
  const confirm = useMutation({
    mutationFn: () => api<PhoneVerified>("/me/phone/verify", { method: "POST", json: { code } }),
    onSuccess: (r) => {
      toast.success(V.phoneDone(r.phone));
      if (r.gift_toman) toast.success(V.giftReceived(f.num(r.gift_toman)));
      setSent(null);
      setEditing(false);
      qc.invalidateQueries({ queryKey: keys.me });
      qc.invalidateQueries({ queryKey: keys.dashboard });
    },
  });

  if (me.phone && me.phone_verified_at && !editing)
    return (
      <div className="flex flex-wrap items-center gap-3">
        <Smartphone className="size-5 text-slate-400" aria-hidden />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-ink-900">{V.phone}</div>
          <div className="num ltr text-sm text-slate-500">{localPhone(me.phone)}</div>
        </div>
        <Badge tone="green">
          <Check aria-hidden />
          {V.verified}
        </Badge>
        <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
          {V.changeNumber}
        </Button>
      </div>
    );

  function sendCode(e: FormEvent) {
    e.preventDefault();
    if (number.trim()) start.mutate();
  }
  function check(e: FormEvent) {
    e.preventDefault();
    if (code.trim()) confirm.mutate();
  }

  return (
    <div className="space-y-4">
      {!sent ? (
        <form onSubmit={sendCode} className="flex flex-wrap items-end gap-3" noValidate>
          <Field label={V.phone} className="min-w-48 flex-1" error={start.error ? errorMessage(start.error, t) : undefined}>
            {(id) => <Input id={id} type="tel" dir="ltr" inputMode="tel" autoComplete="tel" placeholder={V.phonePlaceholder} value={number} onChange={(e) => setNumber(e.target.value)} />}
          </Field>
          <Button type="submit" loading={start.isPending} disabled={!number.trim()}>
            {V.sendCode}
          </Button>
        </form>
      ) : (
        <form onSubmit={check} className="space-y-3" noValidate>
          <Alert kind="success">{V.codeSent(sent.phone, f.num(sent.minutes))}</Alert>
          <div className="flex flex-wrap items-end gap-3">
            <Field label={V.code} className="min-w-40 flex-1" error={confirm.error ? errorMessage(confirm.error, t) : undefined}>
              {(id) => (
                <Input id={id} dir="ltr" inputMode="numeric" autoComplete="one-time-code" maxLength={12} value={code} onChange={(e) => setCode(e.target.value)} autoFocus />
              )}
            </Field>
            <Button type="submit" loading={confirm.isPending} disabled={!code.trim()}>
              {V.confirm}
            </Button>
            <Button variant="ghost" onClick={() => setSent(null)}>
              {V.changeNumber}
            </Button>
          </div>
        </form>
      )}
      <p className="text-sm text-slate-500">{V.viaBot}</p>
    </div>
  );
}

/** Dashboard: the gift and the steps still missing for it (hidden once given). */
export function GiftCard({ gift }: { gift: Dashboard["wallet"]["gift"] }) {
  const { t, f } = useI18n();
  const G = t.launch.gift;
  if (gift.granted || !gift.amount_toman) return null;
  const steps = [
    { done: gift.messenger_linked, label: G.stepLink, action: <LinkButton to="/telegram" size="sm" variant="secondary">{G.linkAction}</LinkButton> },
    ...(gift.phone_required
      ? [{ done: gift.phone_verified, label: G.stepPhone, action: <LinkButton to="/account#phone" size="sm" variant="secondary">{G.phoneAction}</LinkButton> }]
      : []),
  ];
  return (
    <Card className="overflow-hidden ring-brand-200">
      <div className="flex items-start gap-4 p-5 sm:p-6">
        <IconChip tone="solid">
          <Gift />
        </IconChip>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-extrabold text-ink-950">{G.title(f.num(gift.amount_toman))}</h2>
          <p className="mt-1 text-sm text-slate-600">{G.body}</p>
          <ol className="mt-4 space-y-3">
            {steps.map((s) => (
              <li key={s.label} className="flex flex-wrap items-center gap-3">
                <span className={cx("flex size-6 shrink-0 items-center justify-center rounded-full ring-1", s.done ? "bg-emerald-500 text-white ring-emerald-500" : "bg-surface text-slate-400 ring-slate-300")}>
                  {s.done && <Check className="size-4" aria-hidden />}
                </span>
                <span className={cx("min-w-0 flex-1 text-sm font-semibold", s.done ? "text-slate-500 line-through" : "text-ink-900")}>{s.label}</span>
                {!s.done && s.action}
              </li>
            ))}
          </ol>
          <p className="mt-4 text-xs text-slate-500">{G.note}</p>
        </div>
      </div>
    </Card>
  );
}
