import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, CheckCircle2, Images, RefreshCw, ShieldCheck, XCircle } from "lucide-react";
import { api } from "../api/client";
import { keys } from "../api/queries";
import type { InstagramStatus, Posts } from "../api/types";
import { PostCard } from "../components/PostCard";
import { useToast } from "../components/toast";
import { Alert, Badge, Button, Card, CardHeader, ConfirmDialog, PageHeader, PageLoading, cx } from "../components/ui";
import { useI18n } from "../i18n";
import { errorMessage } from "../lib/errors";

/** Fetches a fresh connect link on every click (links expire after 15 minutes) and leaves for Instagram. */
export function useConnectInstagram() {
  const { t } = useI18n();
  const toast = useToast();
  return useMutation({
    mutationFn: () => api<{ url: string }>("/instagram/connect-url"),
    onSuccess: ({ url }) => {
      window.location.href = url;
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });
}

export default function Instagram() {
  const { t, f } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const { data, isPending, error } = useQuery({ queryKey: keys.instagram, queryFn: () => api<InstagramStatus>("/instagram") });
  const connect = useConnectInstagram();

  const disconnect = useMutation({
    mutationFn: () => api("/instagram", { method: "DELETE" }),
    onSuccess: () => {
      setConfirm(false);
      toast.success(t.instagram.disconnected);
      qc.invalidateQueries({ queryKey: keys.instagram });
      qc.invalidateQueries({ queryKey: keys.dashboard });
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  const header = <PageHeader icon={<Camera />} title={t.instagram.title} />;
  if (data && !data.available)
    return (
      <>
        {header}
        <Card className="p-6">
          <h2 className="text-lg font-semibold tracking-tight text-ink-950">{t.launch.instagramSoon.title}</h2>
          <p className="mt-2 max-w-xl text-sm leading-7 text-slate-600">{t.launch.instagramSoon.body}</p>
        </Card>
      </>
    );
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

  const state = !data.connected ? "none" : data.active ? "ok" : "inactive";
  const connectButton = (label: string) => (
    <Button size="lg" onClick={() => connect.mutate()} loading={connect.isPending || connect.isSuccess} icon={<Camera className="size-4" />}>
      {connect.isSuccess ? t.instagram.redirecting : label}
    </Button>
  );

  return (
    <div className="max-w-4xl">
      {header}
      <div className="space-y-6">
        <Card className="animate-pop-in overflow-hidden">
          <div className="flex flex-wrap items-center gap-5 p-5 sm:p-6">
            <span
              aria-hidden
              className={cx(
                "flex size-14 shrink-0 items-center justify-center rounded-2xl",
                state === "ok" ? "bg-brand-600 text-white shadow-md shadow-brand-600/25" : state === "inactive" ? "bg-amber-50 text-amber-600" : "bg-slate-100 text-slate-400",
              )}
            >
              <Camera className="size-7" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-lg font-semibold tracking-tight text-ink-950">
                  {data.connected ? (
                    data.username ? (
                      <a href={`https://instagram.com/${data.username}`} target="_blank" rel="noopener noreferrer" className="ltr hover:text-brand-700 hover:underline">
                        @{data.username}
                      </a>
                    ) : (
                      <span className="ltr">{data.ig_user_id}</span>
                    )
                  ) : (
                    t.nav.instagram
                  )}
                </span>
                {state === "ok" ? (
                  <Badge tone="green">{t.instagram.connected}</Badge>
                ) : state === "inactive" ? (
                  <Badge tone="amber">{t.instagram.inactive}</Badge>
                ) : (
                  <Badge>{t.instagram.notConnected}</Badge>
                )}
              </div>
              {data.connected && data.token_expires_at && (
                <div className="mt-1 text-sm text-slate-500">
                  {t.instagram.tokenExpires}: <span className="font-semibold text-ink-800">{f.date(data.token_expires_at)}</span>
                </div>
              )}
            </div>
          </div>

          {state === "inactive" && (
            <div className="px-5 pb-5 sm:px-6">
              <Alert kind="warning">{t.instagram.inactiveHint}</Alert>
            </div>
          )}

          {state !== "ok" && (
            <div className="border-t border-slate-100 bg-slate-50/60 p-5 sm:p-6">
              <h2 className="font-semibold text-ink-950">{t.panel.instagram.stepsTitle}</h2>
              <ol className="mt-4 space-y-4">
                <li className="flex gap-3.5">
                  <StepNumber n={1} />
                  <p className="pt-1 text-sm leading-6 text-ink-800">{t.instagram.beforeProfessional}</p>
                </li>
                <li className="flex gap-3.5">
                  <StepNumber n={2} />
                  <div className="min-w-0 pt-1 text-sm leading-6 text-ink-800">
                    {t.instagram.beforeMessages}
                    <code className="mt-2 block w-fit max-w-full rounded-lg bg-surface px-3 py-1.5 text-xs leading-5 text-ink-800 ring-1 ring-slate-200" dir="ltr">
                      Settings → Messages and calls → Connected tools → Allow access to messages
                    </code>
                  </div>
                </li>
              </ol>
              <p className="mt-5 flex items-start gap-2 text-sm leading-6 text-slate-500">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden />
                {t.panel.instagram.howItWorks}
              </p>
            </div>
          )}

          {state === "ok" && data.features && (
            <div className="border-t border-slate-100 p-5 sm:p-6">
              <h2 className="text-sm font-semibold text-ink-950">{t.social.instagram.featuresTitle}</h2>
              <ul className="mt-3 grid gap-2.5 sm:grid-cols-2">
                {(["messages", "comments", "stories", "insights"] as const).map((key) => {
                  const on = data.features![key];
                  return (
                    <li key={key} className="flex items-start gap-2.5 text-sm leading-6">
                      {on ? (
                        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden />
                      ) : (
                        <XCircle className="mt-0.5 size-4 shrink-0 text-slate-400" aria-hidden />
                      )}
                      <span className={on ? "text-ink-800" : "text-slate-500"}>
                        {t.social.instagram.features[key]}
                        {!on && <span className="block text-xs text-amber-700">{t.social.instagram.missing}</span>}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 px-5 py-4 sm:px-6">
            {state === "none" && connectButton(t.instagram.connect)}
            {state === "inactive" && connectButton(t.instagram.reconnect)}
            {state === "ok" && data.features && Object.values(data.features).some((on) => !on) && connectButton(t.instagram.reconnect)}
            {data.connected && (
              <Button variant="ghost" onClick={() => setConfirm(true)} className={state === "ok" ? undefined : "sm:ms-auto"}>
                <span className="text-red-700">{t.instagram.disconnect}</span>
              </Button>
            )}
          </div>
        </Card>

        {state === "ok" && <PostsSection />}
      </div>

      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        onConfirm={() => disconnect.mutate()}
        loading={disconnect.isPending}
        danger
        title={t.instagram.disconnectConfirmTitle}
        body={t.instagram.disconnectConfirmBody}
        confirmLabel={t.instagram.disconnect}
        cancelLabel={t.common.cancel}
      />
    </div>
  );
}

function StepNumber({ n }: { n: number }) {
  const { f } = useI18n();
  return (
    <span aria-hidden className="num flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white">
      {f.num(n)}
    </span>
  );
}

/** Which posts the bot can share, and which products it links to each. */
function PostsSection() {
  const { t, f } = useI18n();
  const toast = useToast();
  const qc = useQueryClient();
  const { data, isPending, error } = useQuery({ queryKey: keys.posts, queryFn: () => api<Posts>("/instagram/posts") });
  const sync = useMutation({
    mutationFn: () => api<Posts>("/instagram/posts/sync", { method: "POST" }),
    onSuccess: (posts) => {
      qc.setQueryData(keys.posts, posts);
      toast.success(t.posts.syncedToast);
    },
    onError: (err) => toast.error(errorMessage(err, t)),
  });

  return (
    <Card>
      <CardHeader
        icon={<Images />}
        title={t.posts.title}
        subtitle={t.posts.subtitle}
        action={
          <Button variant="secondary" size="sm" onClick={() => sync.mutate()} disabled={sync.isPending} icon={<RefreshCw className={cx("size-4", sync.isPending && "animate-spin")} />}>
            {t.posts.sync}
          </Button>
        }
      />
      <div className="space-y-4 p-5 text-sm sm:p-6">
        {isPending && <PageLoading />}
        {error && <Alert kind="error">{errorMessage(error, t)}</Alert>}
        {data && (
          <>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-slate-500">
              <Badge tone="brand">{t.posts.total(f.num(data.total))}</Badge>
              <span>{data.synced_at ? t.posts.synced(f.smart(data.synced_at)) : t.posts.neverSynced}</span>
            </div>
            <p className="text-xs leading-6 text-slate-500">{t.posts.howLinked}</p>

            {data.products_without_post.length > 0 && (
              <Alert kind="warning">
                <div className="font-semibold">{t.posts.withoutPost(f.num(data.products_without_post.length))}</div>
                <div className="mt-1 text-xs">{data.products_without_post.join("، ")}</div>
              </Alert>
            )}

            {data.items.length === 0 ? (
              <p className="py-6 text-center text-slate-400">{t.posts.empty}</p>
            ) : (
              <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {data.items.map((post) => (
                  <li key={post.permalink} className="space-y-3 rounded-2xl bg-slate-50/70 p-3 ring-1 ring-slate-200/70">
                    <PostCard post={post} fluid />
                    <div className="flex flex-wrap gap-1.5 px-1">
                      {post.products.length > 0 ? (
                        post.products.map((name) => (
                          <Badge key={name} tone="brand">
                            {name}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-xs text-slate-400">{t.posts.noProduct}</span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
