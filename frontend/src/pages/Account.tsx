import { useEffect, useState, type FormEvent } from "react";
import { useLocation } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { KeyRound, Languages, Store, SunMoon, Trash, TriangleAlert, UserRound } from "lucide-react";
import { api } from "../api/client";
import { useMe } from "../api/queries";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/toast";
import { VerificationCard } from "../components/verify";
import { Alert, Button, Card, CardHeader, ConfirmDialog, Field, IconChip, Input, Modal, PageHeader, PageLoading, Tabs } from "../components/ui";
import { useI18n, type Lang } from "../i18n";
import { errorMessage, fieldError } from "../lib/errors";
import { useTheme, type ThemeChoice } from "../theme";

export default function Account() {
  const { t, lang, setLang } = useI18n();
  const { choice, setChoice } = useTheme();
  const { data: me, isPending, error } = useMe();
  const { hash } = useLocation();

  // /account#phone (from the gift card): bring the phone form into view once it's rendered.
  useEffect(() => {
    if (!me || !hash) return;
    // after the app's own scroll-to-top on navigation
    const timer = setTimeout(() => document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth", block: "center" }), 100);
    return () => clearTimeout(timer);
  }, [me, hash]);

  const header = <PageHeader icon={<UserRound />} title={t.account.title} />;
  if (isPending)
    return (
      <>
        {header}
        <PageLoading />
      </>
    );
  if (error)
    return (
      <>
        {header}
        <Alert kind="error">{errorMessage(error, t)}</Alert>
      </>
    );

  const display = me.full_name || me.email;
  const initial = display.replace(/^[^\p{L}\p{N}]+/u, "").charAt(0).toUpperCase() || "?";

  return (
    <div className="max-w-4xl">
      {header}
      <div className="space-y-6">
        <Card className="animate-pop-in overflow-hidden">
          <div className="flex flex-wrap items-center gap-5 p-5 sm:p-6">
            <span aria-hidden className="flex size-16 shrink-0 items-center justify-center rounded-2xl bg-brand-600 text-2xl font-semibold tracking-tight text-white shadow-md shadow-brand-600/25">
              {initial}
            </span>
            <div className="min-w-0 flex-1">
              {me.full_name && <div className="truncate text-lg font-semibold tracking-tight text-ink-950">{me.full_name}</div>}
              <div className="ltr truncate text-sm font-medium text-slate-500">{me.email}</div>
              <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-semibold text-brand-700 ring-1 ring-brand-100">
                <Store className="size-3.5" aria-hidden />
                <span className="sr-only">{t.account.shop}: </span>
                {me.shop.name}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/60 px-5 py-3 sm:px-6">
            <span className="flex items-center gap-2 text-sm font-semibold text-ink-900">
              <Languages className="size-4 text-slate-400" aria-hidden />
              {t.account.language}
            </span>
            <Tabs<Lang>
              value={lang}
              onChange={setLang}
              items={[
                { value: "ar", label: <span lang="ar">العربية</span> },
                { value: "en", label: <span lang="en">English</span> },
              ]}
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/60 px-5 py-3 sm:px-6">
            <span className="flex items-center gap-2 text-sm font-semibold text-ink-900">
              <SunMoon className="size-4 text-slate-400" aria-hidden />
              {t.theme.title}
            </span>
            <Tabs<ThemeChoice>
              value={choice}
              onChange={setChoice}
              items={[
                { value: "light", label: t.theme.light },
                { value: "dark", label: t.theme.dark },
                { value: "system", label: t.theme.system },
              ]}
            />
          </div>
        </Card>

        <VerificationCard me={me} />
        <ChangePassword />
        <DeleteAccount />
      </div>
    </div>
  );
}

function ChangePassword() {
  const { t } = useI18n();
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");

  const change = useMutation({
    mutationFn: () => api("/me/password", { method: "POST", json: { current_password: current, new_password: next } }),
    onSuccess: () => {
      toast.success(t.account.passwordChanged);
      setCurrent("");
      setNext("");
      setRepeat("");
    },
  });

  const short = next.length > 0 && next.length < 8;
  const mismatch = repeat.length > 0 && repeat !== next;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!short && !mismatch && current && next === repeat) change.mutate();
  }

  const hasFieldErrors = change.error && fieldError(change.error, "new_password", t);

  return (
    <Card>
      <CardHeader icon={<KeyRound />} title={t.account.changePassword} />
      <form onSubmit={submit} className="space-y-4 p-5 sm:p-6" noValidate>
        {change.error && !hasFieldErrors && <Alert kind="error">{errorMessage(change.error, t)}</Alert>}
        <Field label={t.account.currentPassword}>
          {(id) => <Input id={id} type="password" dir="ltr" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />}
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label={t.account.newPassword} hint={t.auth.passwordHint} error={short ? t.errors.field.new_password : fieldError(change.error, "new_password", t)}>
            {(id) => (
              <Input id={id} type="password" dir="ltr" autoComplete="new-password" maxLength={128} invalid={short} value={next} onChange={(e) => setNext(e.target.value)} />
            )}
          </Field>
          <Field label={t.account.repeatPassword} error={mismatch ? t.account.passwordMismatch : undefined}>
            {(id) => (
              <Input id={id} type="password" dir="ltr" autoComplete="new-password" invalid={mismatch} value={repeat} onChange={(e) => setRepeat(e.target.value)} />
            )}
          </Field>
        </div>
        <div className="flex justify-end border-t border-slate-100 pt-4">
          <Button type="submit" loading={change.isPending} disabled={!current || next.length < 8 || next !== repeat}>
            {t.account.changePassword}
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** Two-step confirmation: "are you sure?" then password + typed confirmation word. */
function DeleteAccount() {
  const { t } = useI18n();
  const { logout } = useAuth();
  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [password, setPassword] = useState("");
  const [word, setWord] = useState("");

  const remove = useMutation({
    // DELETE with a JSON body (fine with fetch)
    mutationFn: () => api("/me", { method: "DELETE", json: { password } }),
    onSuccess: () => logout(),
  });

  const close = () => {
    setStep(0);
    setPassword("");
    setWord("");
    remove.reset();
  };

  const wordOk = word.trim().toLowerCase() === t.account.deleteWord.toLowerCase();

  return (
    <Card danger>
      <div className="flex flex-wrap items-start gap-4 p-5 sm:p-6">
        <IconChip tone="red">
          <TriangleAlert />
        </IconChip>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-red-700">{t.account.deleteTitle}</h2>
          <p className="mt-1 text-sm leading-7 text-slate-600">{t.account.deleteDesc}</p>
        </div>
        <Button variant="danger" icon={<Trash className="size-4" />} onClick={() => setStep(1)}>
          {t.account.deleteButton}
        </Button>
      </div>

      <ConfirmDialog
        open={step === 1}
        onClose={close}
        onConfirm={() => setStep(2)}
        danger
        title={t.account.deleteStep1Title}
        body={t.account.deleteStep1Body}
        confirmLabel={t.account.deleteStep1Continue}
        cancelLabel={t.common.cancel}
      />

      <Modal
        open={step === 2}
        onClose={close}
        title={t.account.deleteStep2Title}
        footer={
          <>
            <Button variant="secondary" onClick={close}>
              {t.common.cancel}
            </Button>
            <Button variant="danger" loading={remove.isPending} disabled={!password || !wordOk} onClick={() => remove.mutate()}>
              {t.account.deleteFinal}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <p className="text-sm leading-7 text-slate-600">{t.account.deleteStep2Body(t.account.deleteWord)}</p>
          {remove.error && <Alert kind="error">{errorMessage(remove.error, t)}</Alert>}
          <Field label={t.auth.password}>
            {(id) => <Input id={id} type="password" dir="ltr" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}
          </Field>
          <Field label={t.account.deleteWordLabel}>{(id) => <Input id={id} value={word} onChange={(e) => setWord(e.target.value)} />}</Field>
        </div>
      </Modal>
    </Card>
  );
}
