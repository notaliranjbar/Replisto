import type { ReactNode } from "react";
import { AtSign, Bot, CircleDashed, FileIcon, Image, MessageCircleMore, Mic, Paperclip, Share2, Smile, UserRound, Video } from "lucide-react";
import type { Message } from "../api/types";
import { useI18n } from "../i18n";
import { PostCard, sharedPostUrl } from "./PostCard";
import { customerName } from "../lib/format";
import { Badge, cx } from "./ui";

/** Pause set "until resumed by hand" is stored as ~10 years ahead. */
export function isIndefinitePause(until: string | null): boolean {
  return !!until && new Date(until).getTime() - Date.now() > 365 * 24 * 3600 * 1000;
}

export function useCustomerName() {
  const { t, f } = useI18n();
  return (username: string | null | undefined, igsid: string, name?: string | null) => customerName(username, igsid, t, f, name);
}

export function Avatar({ name, className, solid }: { name: string; className?: string; solid?: boolean }) {
  const letter = name.replace(/^[^\p{L}\p{N}]+/u, "").charAt(0).toUpperCase() || "?";
  return (
    <span
      aria-hidden
      className={cx(
        "flex size-10 shrink-0 items-center justify-center rounded-full font-semibold transition-colors",
        solid ? "bg-brand-600 text-white" : "bg-brand-100 text-brand-700",
        className,
      )}
    >
      {letter}
    </span>
  );
}

// "[image]", or "[story_reply: what the story showed]"
const MARKER = /\[([a-z_]+)(?::\s*([^\]]*))?\]/g;

/** Message text with `[image]`/`[audio]`… markers (media the customer sent) shown as chips. */
export function MessageText({ text }: { text: string }) {
  const { t } = useI18n();
  const labels: Record<string, [string, ReactNode]> = {
    image: [t.inbox.image, <Image key="i" className="size-3.5" />],
    photo: [t.inbox.image, <Image key="ph" className="size-3.5" />],
    voice: [t.inbox.audio, <Mic key="vo" className="size-3.5" />],
    gif: [t.inbox.sticker, <Smile key="g" className="size-3.5" />],
    audio: [t.inbox.audio, <Mic key="a" className="size-3.5" />],
    video: [t.inbox.video, <Video key="v" className="size-3.5" />],
    ig_reel: [t.inbox.video, <Video key="r" className="size-3.5" />],
    reel: [t.inbox.video, <Video key="r2" className="size-3.5" />],
    file: [t.inbox.attachment, <FileIcon key="f" className="size-3.5" />],
    sticker: [t.inbox.sticker, <Smile key="s" className="size-3.5" />],
    animated_image: [t.inbox.sticker, <Smile key="s2" className="size-3.5" />],
    story_reply: [t.social.markers.story_reply, <CircleDashed key="sr" className="size-3.5" />],
    story_mention: [t.social.markers.story_mention, <AtSign key="sm" className="size-3.5" />],
    comment: [t.social.markers.comment, <MessageCircleMore key="c" className="size-3.5" />],
    share: [t.social.markers.share, <Share2 key="sh" className="size-3.5" />],
    ig_post: [t.social.markers.ig_post, <Image key="ip" className="size-3.5" />],
  };

  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(MARKER)) {
    const idx = m.index ?? 0;
    if (idx > last) parts.push(text.slice(last, idx));
    const [label, icon] = labels[m[1]] ?? [m[1], <Paperclip key="p" className="size-3.5" />];
    parts.push(
      <span key={idx} className="mx-0.5 inline-flex max-w-full items-center gap-1 rounded-md bg-black/5 px-1.5 py-0.5 align-middle text-xs" title={m[2] || undefined}>
        {icon}
        <span className="truncate">
          {label}
          {m[2] ? `: ${m[2]}` : ""}
        </span>
      </span>,
    );
    last = idx + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}

/** One-line preview for lists (markers become labels). */
export function useMessagePreview() {
  const { t } = useI18n();
  const labels: Record<string, string> = {
    image: t.inbox.image,
    photo: t.inbox.image,
    audio: t.inbox.audio,
    voice: t.inbox.audio,
    video: t.inbox.video,
    sticker: t.inbox.sticker,
    file: t.inbox.attachment,
    story_reply: t.social.markers.story_reply,
    story_mention: t.social.markers.story_mention,
    comment: t.social.markers.comment,
    share: t.social.markers.share,
  };
  return (text: string) => text.replace(MARKER, (_, k: string) => `(${labels[k] ?? k})`).replace(/\s+/g, " ").trim();
}

/**
 * customer: start side (right in RTL), neutral
 * bot:      end side, brand colour + bot icon
 * owner:    end side, different colour + "You" label
 */
export function MessageBubble({ message, animate }: { message: Message; animate?: boolean }) {
  const { t, f } = useI18n();
  const mine = message.sender !== "customer";
  const post = message.sender === "bot" ? sharedPostUrl(message.text) : null;

  return (
    <div className={cx("flex flex-col gap-1", mine ? "items-end" : "items-start", animate && "animate-msg-in")}>
      <div className={cx("flex max-w-[85%] items-end gap-2 sm:max-w-[70%]", mine && "flex-row-reverse")}>
        {message.sender === "bot" && (
          <span className="mb-1 flex size-6 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700">
            <Bot className="size-3.5" />
          </span>
        )}
        {message.sender === "owner" && (
          <span className="mb-1 flex size-6 shrink-0 items-center justify-center rounded-full bg-night-900 text-white">
            <UserRound className="size-3.5" />
          </span>
        )}
        {post !== null ? (
          <PostCard post={{ permalink: post }} />
        ) : (
          <div
            className={cx(
              "user-text rounded-2xl px-4 py-2.5 text-sm leading-7",
              message.sender === "customer" && "rounded-ss-md bg-surface text-ink-900 shadow-sm ring-1 ring-line",
              message.sender === "bot" && "rounded-se-md bg-brand-600 text-white",
              message.sender === "owner" && "rounded-se-md bg-night-900 text-white dark:bg-night-800 dark:ring-1 dark:ring-white/10",
            )}
          >
            <MessageText text={message.text} />
          </div>
        )}
      </div>
      <div className={cx("flex items-center gap-2 text-[11px] text-slate-400", mine ? "me-8" : "ms-1")}>
        {message.sender === "owner" && <span className="font-semibold text-ink-800">{t.inbox.senderOwner}</span>}
        {message.sender === "bot" && <span>{t.inbox.senderBot}</span>}
        <span title={f.dateTime(message.created_at)}>{f.smart(message.created_at)}</span>
        {message.unanswered && <Badge tone="amber">{t.inbox.botDidntKnow}</Badge>}
      </div>
    </div>
  );
}
