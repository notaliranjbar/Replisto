import { useEffect } from "react";
import { useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { keys } from "../api/queries";
import { Button, Card, LinkButton, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { useConnectInstagram } from "./Instagram";

// The backend redirects here after Instagram's permission screen:
// ?status=connected | denied | error (&reason=account_in_use | invalid_state | instagram | missing_code)

export default function InstagramCallback() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const connect = useConnectInstagram();
  const status = params.get("status");
  const reason = params.get("reason");

  useEffect(() => {
    qc.invalidateQueries({ queryKey: keys.instagram });
    qc.invalidateQueries({ queryKey: keys.dashboard });
  }, [qc]);

  const ok = status === "connected";
  let title: string;
  let hint: string | null = null;
  if (ok) {
    title = t.callback.connected;
    hint = t.callback.connectedHint;
  } else if (status === "denied") {
    title = t.callback.denied;
    hint = t.callback.deniedHint;
  } else if (reason === "account_in_use") {
    title = t.callback.accountInUse;
  } else if (reason === "invalid_state") {
    title = t.callback.invalidState;
  } else {
    title = t.callback.instagramError;
  }

  return (
    <div className="mx-auto max-w-md pt-6 sm:pt-12">
      <Card className="animate-pop-in flex flex-col items-center px-6 py-10 text-center sm:px-10">
        <span
          aria-hidden
          className={cx(
            "flex size-16 items-center justify-center rounded-full ring-8",
            ok ? "bg-emerald-500 text-white ring-emerald-100" : "bg-red-500 text-white ring-red-100",
          )}
        >
          {ok ? <Check className="size-8" strokeWidth={3} /> : <X className="size-8" strokeWidth={3} />}
        </span>
        <h1 className="mt-6 text-xl font-semibold tracking-tight text-ink-950">{title}</h1>
        {hint && <p className="mt-2 text-sm leading-7 text-slate-500">{hint}</p>}
        <div className="mt-8 flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:justify-center">
          {ok ? (
            <LinkButton to="/knowledge" size="lg">
              {t.callback.nextStep}
            </LinkButton>
          ) : (
            <>
              {reason !== "account_in_use" && (
                <Button size="lg" onClick={() => connect.mutate()} loading={connect.isPending || connect.isSuccess}>
                  {t.callback.tryAgain}
                </Button>
              )}
              <LinkButton to="/instagram" size="lg" variant="secondary">
                {t.callback.backToInstagram}
              </LinkButton>
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
