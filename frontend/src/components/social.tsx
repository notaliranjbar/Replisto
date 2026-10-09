import { Camera, Film, Images, Image as ImageIcon, Megaphone } from "lucide-react";
import { useConnectInstagram } from "../pages/Instagram";
import { useI18n } from "../i18n";
import { Button, LinkButton, cx } from "./ui";

/** Shown above Comments / Stories / Insights when Instagram can't do that yet. */
export function InstagramNotice({ connected, needsReconnect }: { connected: boolean; needsReconnect: boolean }) {
  const { t } = useI18n();
  const connect = useConnectInstagram();
  if (connected && !needsReconnect) return null;
  return (
    <div className="mb-6 flex flex-wrap items-center gap-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3.5 text-sm text-amber-900">
      <Camera className="size-5 shrink-0 text-amber-600" aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="font-semibold">{needsReconnect ? t.social.reconnect.title : t.social.reconnect.notConnected}</div>
        {needsReconnect && <p className="mt-0.5 leading-6 text-amber-800">{t.social.reconnect.body}</p>}
      </div>
      {needsReconnect ? (
        <Button size="sm" variant="secondary" loading={connect.isPending} onClick={() => connect.mutate()}>
          {t.social.reconnect.action}
        </Button>
      ) : (
        <LinkButton to="/instagram" size="sm" variant="secondary">
          {t.social.reconnect.connect}
        </LinkButton>
      )}
    </div>
  );
}

const FORMAT_ICONS = { reel: Film, carousel: Images, video: Film, photo: ImageIcon, post: ImageIcon, ad: Megaphone } as const;

/** A post's picture, or a quiet tile with its format icon when Instagram gave none. */
export function PostThumb({
  src,
  format = "post",
  className,
}: {
  src?: string | null;
  format?: keyof typeof FORMAT_ICONS;
  className?: string;
}) {
  const Icon = FORMAT_ICONS[format] ?? ImageIcon;
  return src ? (
    <img src={src} alt="" loading="lazy" className={cx("shrink-0 rounded-md border border-slate-200 bg-slate-100 object-cover", className)} />
  ) : (
    <span aria-hidden className={cx("flex shrink-0 items-center justify-center rounded-md border border-slate-200 bg-slate-50 text-slate-400", className)}>
      <Icon className="size-1/2 max-h-6 max-w-6" />
    </span>
  );
}
