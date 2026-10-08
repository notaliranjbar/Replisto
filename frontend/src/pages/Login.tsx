import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import AuthShell from "../components/AuthShell";
import { Alert, Button, Field, Input } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage, fieldError } from "../lib/errors";

export default function Login() {
  const { t } = useI18n();
  const { login, expired } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      const next = params.get("next");
      navigate(next && next.startsWith("/") && !next.startsWith("//") ? next : "/", { replace: true });
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  const hasFieldErrors = error instanceof ApiError && Object.keys(error.fields).length > 0;
  let message: string | null = null;
  if (error != null && !hasFieldErrors) {
    // show our own, translated text for the common case
    message = error instanceof ApiError && error.status === 401 ? t.auth.wrongCredentials : errorMessage(error, t);
  }

  return (
    <AuthShell
      title={t.auth.loginTitle}
      subtitle={t.auth.loginSubtitle}
      footer={
        <>
          {t.auth.noAccount}{" "}
          <Link to="/register" className="font-medium text-brand-700 hover:underline">
            {t.auth.goRegister}
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        {expired && error == null && <Alert kind="info">{t.auth.sessionExpired}</Alert>}
        {message && <Alert kind="error">{message}</Alert>}
        <Field label={t.auth.email} error={fieldError(error, "email", t)}>
          {(id) => (
            <Input id={id} type="email" dir="ltr" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          )}
        </Field>
        <Field label={t.auth.password} error={fieldError(error, "password", t)}>
          {(id) => (
            <Input
              id={id}
              type="password"
              dir="ltr"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <div className="-mt-1 text-end">
          <Link to="/forgot-password" className="text-sm font-medium text-brand-700 hover:underline">
            {t.launch.password.forgotLink}
          </Link>
        </div>
        <Button type="submit" loading={busy} className="w-full" disabled={!email || !password}>
          {t.auth.login}
        </Button>
      </form>
    </AuthShell>
  );
}
